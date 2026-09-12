"""F4 — Chunking estructural para el corpus jurídico.

Estrategia (alineada con la propuesta: *chunking estructural* + *por tamaño con
solape* como respaldo):

1. Se detectan unidades estructurales del texto normativo: ``TÍTULO``,
   ``CAPÍTULO``, ``SECCIÓN`` y, sobre todo, ``Artículo N`` / ``Artículo Único``.
2. Cada artículo es un chunk semántico natural (unidad de cita legal).
3. Si el artículo excede ``CHUNK_MAX_CHARS`` se subdivide con solape.
4. Si el documento no tiene estructura detectable se aplica chunking por
   tamaño con solape.

Salida: ``data/processed/chunks.jsonl`` (un registro por chunk, listo para NER
y embeddings).
"""
from __future__ import annotations

import hashlib
import json
import re

from config import settings

# --- Patrones estructurales (español jurídico) ---
RE_ARTICULO = re.compile(
    r"(?im)^\s*(art[íi]culo|art\.?)\s*"
    r"(\d+(?:\s*(?:bis|ter|quáter|quinquies))?|[úu]nico)\b[.:°º\-]?\s*"
)
RE_TITULO = re.compile(r"(?im)^\s*(t[íi]tulo)\s+([IVXLCDM]+|\d+)\b")
RE_CAPITULO = re.compile(r"(?im)^\s*(cap[íi]tulo)\s+([IVXLCDM]+|\d+)\b")
RE_SECCION = re.compile(r"(?im)^\s*(secci[óo]n)\s+([IVXLCDM]+|\d+|[a-z])\b")


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _recortar(texto: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _dividir_por_tamano(texto: str, max_chars: int, overlap: int) -> list[str]:
    """Divide un bloque largo respetando límites de palabra."""
    partes, inicio = [], 0
    n = len(texto)
    while inicio < n:
        fin = min(inicio + max_chars, n)
        if fin < n:
            corte = texto.rfind(" ", inicio + int(max_chars * 0.6), fin)
            if corte > inicio:
                fin = corte
        partes.append(texto[inicio:fin].strip())
        if fin >= n:
            break
        inicio = max(fin - overlap, inicio + 1)
    return [p for p in partes if p]


def _contexto(texto: str, pos: int) -> str:
    """Etiqueta jerárquica vigente (Título/Capítulo/Sección) antes de ``pos``."""
    etiquetas: dict[str, str] = {}
    for pat, clave in ((RE_TITULO, "titulo"), (RE_CAPITULO, "capitulo"), (RE_SECCION, "seccion")):
        ultimo = None
        for m in pat.finditer(texto[:pos]):
            ultimo = f"{m.group(1).capitalize()} {m.group(2)}"
        if ultimo:
            etiquetas[clave] = ultimo
    return " · ".join(etiquetas.values())


def _chunks_estructurales(texto: str) -> list[dict]:
    matches = list(RE_ARTICULO.finditer(texto))
    chunks: list[dict] = []

    # Preámbulo (antes del primer artículo)
    if matches:
        pre = _recortar(texto[: matches[0].start()])
        if len(pre) >= settings.CHUNK_MIN_CHARS:
            if len(pre) <= settings.CHUNK_MAX_CHARS:
                chunks.append({"seccion": "Preámbulo", "texto": pre})
            else:
                for j, parte in enumerate(
                    _dividir_por_tamano(pre, settings.CHUNK_MAX_CHARS, settings.CHUNK_OVERLAP_CHARS)
                ):
                    chunks.append({"seccion": f"Preámbulo (parte {j + 1})", "texto": parte})

    for i, m in enumerate(matches):
        inicio = m.start()
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        cuerpo = _recortar(texto[inicio:fin])
        if len(cuerpo) < 30:
            continue
        numero = re.sub(r"\s+", " ", m.group(2)).strip().upper()
        etiqueta = f"Artículo {numero}"
        ctx = _contexto(texto, inicio)
        if ctx:
            etiqueta = f"{ctx} · {etiqueta}"
        if len(cuerpo) <= settings.CHUNK_MAX_CHARS:
            chunks.append({"seccion": etiqueta, "texto": cuerpo})
        else:
            for j, parte in enumerate(
                _dividir_por_tamano(cuerpo, settings.CHUNK_MAX_CHARS, settings.CHUNK_OVERLAP_CHARS)
            ):
                chunks.append({"seccion": f"{etiqueta} (parte {j + 1})", "texto": parte})
    return chunks


def _chunks_por_tamano(texto: str) -> list[dict]:
    partes = _dividir_por_tamano(texto, settings.CHUNK_MAX_CHARS, settings.CHUNK_OVERLAP_CHARS)
    return [{"seccion": f"Fragmento {i + 1}", "texto": p} for i, p in enumerate(partes)]


def chunk_document(doc: dict) -> list[dict]:
    """Genera los chunks de un documento (dict de ``extracted.jsonl``)."""
    texto = _recortar(doc.get("texto", ""))
    if not texto:
        return []
    estrategia = "estructural"
    base = _chunks_estructurales(texto)
    if len(base) <= 1:  # sin estructura aprovechable
        estrategia = "tamano"
        base = _chunks_por_tamano(texto)

    # Red de seguridad: ningún chunk debe exceder CHUNK_MAX_CHARS
    plano: list[dict] = []
    for c in base:
        if len(c["texto"]) <= settings.CHUNK_MAX_CHARS:
            plano.append(c)
        else:
            for j, parte in enumerate(
                _dividir_por_tamano(c["texto"], settings.CHUNK_MAX_CHARS, settings.CHUNK_OVERLAP_CHARS)
            ):
                plano.append({"seccion": f"{c['seccion']} (parte {j + 1})", "texto": parte})

    salida = []
    for idx, c in enumerate(plano):
        t = c["texto"]
        if len(t) < settings.CHUNK_MIN_CHARS and len(plano) > 1:
            continue
        salida.append({
            "doc_id": doc["doc_id"],
            "titulo": doc.get("titulo"),
            "fuente_url": doc.get("fuente_url"),
            "tipo_norma": doc.get("tipo_norma"),
            "materia": doc.get("materia"),
            "formato": doc.get("formato"),
            "estrategia": estrategia,
            "chunk_index": idx,
            "seccion": c["seccion"],
            "texto": t,
            "n_caracteres": len(t),
            "doc_hash": _sha(t),
        })
    return salida


def run() -> list[dict]:
    src = settings.PROCESSED_DIR / "extracted.jsonl"
    if not src.exists():
        raise SystemExit("No hay extracted.jsonl. Ejecuta primero: python -m src.extract")

    docs = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    todos: list[dict] = []
    for doc in docs:
        cs = chunk_document(doc)
        todos.extend(cs)
        print(f"  {doc['doc_id']:8s} {doc.get('titulo','')[:44]:<44} -> {len(cs):>3d} chunks")

    out = settings.PROCESSED_DIR / "chunks.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for c in todos:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    n_est = sum(1 for c in todos if c["estrategia"] == "estructural")
    print(f"\nResumen chunking: {len(todos)} chunks de {len(docs)} documentos "
          f"({n_est} estructurales, {len(todos) - n_est} por tamaño)")
    print(f"Salida: {out}")
    return todos


if __name__ == "__main__":
    run()
