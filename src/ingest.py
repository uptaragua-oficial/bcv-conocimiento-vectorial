"""F2 — Ingesta del corpus jurídico del BCV.

Descarga, preserva y registra:
  1. Las páginas HTML de las secciones normativas (marco legal, convenios,
     resoluciones, actos administrativos, sistema de pagos).
  2. Los documentos enlazados (PDF / Word / Excel) de esas páginas.

Salidas:
  * ``data/raw/<slug>.html``      → artefactos HTML originales
  * ``data/raw/docs/<archivo>``   → documentos originales
  * ``data/raw/manifest.json``    → índice de páginas (URL, hash, fecha)
  * ``data/raw/documentos.json``  → índice de documentos (URL, formato, bytes)
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from config import settings

# Secciones del dominio jurídico del portal del BCV.
SEEDS: list[str] = [
    # Marco jurídico
    "/marco/leyes_bcv",
    "/marco/convenios-cambiarios",
    "/marco/decreto-reglamentos-resolucion-cambiaria",
    "/marco/decreto-reglamentos-resolucion-monetaria",
    "/marco/decreto-reglamentos-resolucion-pago",
    "/marco/decreto-reglamentos-resolucion-minerales",
    # Sistema de pagos
    "/sistema-de-pagos/aspectos-legales/actos-administrativos",
    "/sistema-de-pagos/cce/actos-administrativos",
    "/sistemas-de-pago/documentos",
    # Actos administrativos por materia (79 documentos que antes quedaban fuera).
    # Se añadieron tras comprobar que las ocho secciones existen y no se
    # ingestaban: son circulares que regulan la operativa de las instituciones.
    "/actos-adm-moneda-ext",
    "/actos-adm-encaje-legal",
    "/actos-adm-operaciones-mercado-abierto",
    "/actos-adm-asistencia-financiera",
    "/actos-adm-politica-monetaria-agente-financiero",
    "/actos-adm-sinex",
    "/actos-adm-instrumento-directo-bcv",
    "/actos-adm-turismo",
]

DOC_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods")
# Prefijos internos que se rastrean en profundidad 1 (páginas hijas).
FOLLOW_PREFIXES = (
    "/marco/",
    "/sistema-de-pagos/",
    "/sistemas-de-pago/",
    "/actos-adm",
)

HEADERS = {"User-Agent": settings.USER_AGENT, "Accept-Language": "es-VE,es;q=0.9"}


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def _slug(url: str) -> str:
    path = urlparse(url).path.strip("/") or "index"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", path.replace("/", "_"))[:120]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def _get(session, url: str, *, binary: bool = False):
    import urllib3

    if not settings.VERIFY_SSL:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    resp = session.get(url, timeout=60, verify=settings.VERIFY_SSL)
    resp.raise_for_status()
    return resp.content if binary else resp.text


# ----------------------------------------------------------------------
# Ingesta
# ----------------------------------------------------------------------
def _links(html: str, base_url: str) -> tuple[list[str], list[str]]:
    """Separa enlaces internos (páginas) y documentos."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    pages, docs = set(), set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc and "bcv.org.ve" not in parsed.netloc:
            continue
        path = parsed.path.lower()
        if path.endswith(DOC_EXT):
            docs.add(absolute)
        elif parsed.netloc == "" or "bcv.org.ve" in parsed.netloc:
            pages.add(absolute)
    return sorted(pages), sorted(docs)


def _follow(url: str) -> bool:
    path = urlparse(url).path
    return any(path.startswith(p) for p in FOLLOW_PREFIXES)


def run(limit_pages: int = 120, limit_docs: int = 600, delay: float | None = None) -> dict:
    """Ejecuta la ingesta y devuelve un resumen."""
    delay = settings.REQUEST_DELAY_SECONDS if delay is None else delay
    session = _session()
    manifest: list[dict] = []
    documentos: list[dict] = []
    seen_pages: set[str] = set()
    seen_docs: set[str] = set()
    queue = [urljoin(settings.BCV_BASE_URL, s) for s in SEEDS]
    doc_dir = settings.RAW_DIR / "docs"
    doc_dir.mkdir(parents=True, exist_ok=True)

    print(f"Ingesta del dominio jurídico — {len(queue)} semillas\n")

    while queue and len(seen_pages) < limit_pages:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        try:
            html = _get(session, url)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR  {url} -> {exc}")
            seen_pages.add(url)
            continue

        seen_pages.add(url)
        slug = _slug(url)
        path = settings.RAW_DIR / f"{slug}.html"
        path.write_text(html, encoding="utf-8")
        pages, docs = _links(html, url)

        manifest.append(
            {
                "id": f"pg_{len(manifest)+1:04d}",
                "url": url,
                "archivo": path.name,
                "titulo": slug,
                "hash": _sha256(html.encode("utf-8")),
                "n_bytes": len(html.encode("utf-8")),
                "n_enlaces_docs": len(docs),
                "fecha_captura": _now(),
                "estado": "ok",
            }
        )
        print(f"  OK     {slug:<55} docs={len(docs):>2}")

        for p in pages:
            if _follow(p) and p not in seen_pages and len(queue) + len(seen_pages) < limit_pages:
                queue.append(p)

        for d in docs:
            if d in seen_docs or len(seen_docs) >= limit_docs:
                continue
            seen_docs.add(d)
            fname = Path(urlparse(d).path).name or _slug(d)
            destino = doc_dir / fname
            # Reanudable: si ya está descargado y no está vacío, no se repite.
            # Un corte a mitad de ingesta solo cuesta el documento en curso.
            if destino.exists() and destino.stat().st_size > 0:
                documentos.append(
                    {
                        "id": f"doc_{len(documentos)+1:04d}",
                        "url": d,
                        "archivo": fname,
                        "ext": Path(fname).suffix.lower(),
                        "origen": _slug(url),
                        "bytes": destino.stat().st_size,
                        "hash": _sha256(destino.read_bytes()),
                        "fecha_captura": _now(),
                        "estado": "ok",
                        "cacheado": True,
                    }
                )
                continue
            try:
                content = _get(session, d, binary=True)
            except Exception as exc:  # noqa: BLE001
                documentos.append({"url": d, "estado": f"error: {exc}", "ext": Path(urlparse(d).path).suffix})
                continue
            destino.write_bytes(content)
            documentos.append(
                {
                    "id": f"doc_{len(documentos)+1:04d}",
                    "url": d,
                    "archivo": fname,
                    "ext": Path(fname).suffix.lower(),
                    "origen": _slug(url),
                    "bytes": len(content),
                    "hash": _sha256(content),
                    "fecha_captura": _now(),
                    "estado": "ok",
                }
            )
            time.sleep(delay * 0.5)

        time.sleep(delay)

    (settings.RAW_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (settings.RAW_DIR / "documentos.json").write_text(
        json.dumps(documentos, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok_docs = [d for d in documentos if d.get("estado") == "ok"]
    resumen = {
        "paginas": len(manifest),
        "documentos": len(ok_docs),
        "documentos_error": len(documentos) - len(ok_docs),
        "por_formato": {},
    }
    for d in ok_docs:
        resumen["por_formato"][d["ext"]] = resumen["por_formato"].get(d["ext"], 0) + 1

    print(f"\nResumen ingesta: {resumen['paginas']} páginas · {resumen['documentos']} documentos "
          f"({resumen['por_formato']}) · {resumen['documentos_error']} errores")
    return resumen


if __name__ == "__main__":
    run()
