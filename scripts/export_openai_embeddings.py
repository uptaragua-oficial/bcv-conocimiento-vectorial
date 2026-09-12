"""Vectoriza el corpus con una API de embeddings (compatible con OpenAI).

Genera, para el modo nativo de Vercel:
  * ``web/api/_data/vectors.f32``          — matriz Float32 little-endian (N × D)
  * ``web/api/_data/embeddings_meta.json`` — dimensiones, modelo y proveedor

El orden de los vectores coincide **exactamente** con el de los fragmentos de
``web/api/_data/corpus.json``, que es lo que garantiza que la similitud coseno
en tiempo de consulta apunte al fragmento correcto.

Compatible con OpenAI, DeepInfra, Jina, Voyager, etc. (todos exponen
``POST /embeddings`` con el formato de OpenAI).

Uso:
  export EMBEDDINGS_API_KEY=sk-...
  python -m scripts.export_openai_embeddings

Variables:
  EMBEDDINGS_API_KEY / OPENAI_API_KEY   clave (obligatoria)
  EMBEDDINGS_BASE_URL                   por defecto https://api.openai.com/v1
  EMBEDDINGS_MODEL                      por defecto text-embedding-3-small
  EMBEDDINGS_DIMENSIONS                 opcional; reduce la dimensionalidad
  EMBEDDINGS_BATCH                      tamaño de lote (por defecto 256)
"""
from __future__ import annotations

import json
import os
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / "web" / "api" / "_data" / "corpus.json"
VECTORES = RAIZ / "web" / "api" / "_data" / "vectors.f32"
META = RAIZ / "web" / "api" / "_data" / "embeddings_meta.json"


def _config() -> dict:
    clave = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not clave:
        raise SystemExit(
            "Falta EMBEDDINGS_API_KEY (o OPENAI_API_KEY).\n"
            "Ejemplo:  export EMBEDDINGS_API_KEY=sk-..."
        )
    base = (os.getenv("EMBEDDINGS_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    cfg = {
        "clave": clave,
        "url": f"{base}/embeddings",
        "modelo": os.getenv("EMBEDDINGS_MODEL") or "text-embedding-3-small",
        "lote": int(os.getenv("EMBEDDINGS_BATCH") or 256),
    }
    dims = os.getenv("EMBEDDINGS_DIMENSIONS")
    if dims:
        cfg["dimensions"] = int(dims)
    return cfg


def _embeber(cfg: dict, textos: list[str]) -> list[list[float]]:
    import requests

    payload: dict = {"model": cfg["modelo"], "input": textos}
    if cfg.get("dimensions"):
        payload["dimensions"] = cfg["dimensions"]

    for intento in range(4):
        resp = requests.post(
            cfg["url"],
            headers={
                "Authorization": f"Bearer {cfg['clave']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            espera = 2 ** intento
            print(f"    HTTP {resp.status_code}; reintento en {espera}s")
            time.sleep(espera)
            continue
        resp.raise_for_status()
        datos = resp.json()["data"]
        datos.sort(key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in datos]
    raise SystemExit(f"La API de embeddings falló tras varios intentos ({resp.status_code})")


def run() -> dict:
    if not CORPUS.exists():
        raise SystemExit(
            f"No existe {CORPUS}. Ejecuta primero:\n"
            "  python -m scripts.export_vercel_index"
        )

    cfg = _config()
    datos = json.loads(CORPUS.read_text(encoding="utf-8"))
    docs = datos["docs"]
    textos = [d[6] for d in docs]
    print(f"Vectorizando {len(textos)} fragmentos con {cfg['modelo']} ({cfg['url']})")

    vectores: list[list[float]] = []
    for i in range(0, len(textos), cfg["lote"]):
        lote = textos[i : i + cfg["lote"]]
        vectores.extend(_embeber(cfg, lote))
        print(f"  {min(i + cfg['lote'], len(textos))}/{len(textos)}")
        time.sleep(0.2)

    if len(vectores) != len(textos):
        raise SystemExit(f"Desajuste: {len(vectores)} vectores para {len(textos)} fragmentos")

    dim = len(vectores[0])
    if any(len(v) != dim for v in vectores):
        raise SystemExit("Los vectores no tienen todos la misma dimensión")

    # Normalización L2 → la similitud coseno es un simple producto punto.
    with VECTORES.open("wb") as f:
        for v in vectores:
            norma = sum(x * x for x in v) ** 0.5 or 1.0
            f.write(struct.pack(f"<{dim}f", *[x / norma for x in v]))

    meta = {
        "n": len(vectores),
        "dim": dim,
        "modelo": cfg["modelo"],
        "url": cfg["url"],
        "normalizado": "l2",
        "generado": datetime.now(timezone.utc).isoformat(),
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    mb = VECTORES.stat().st_size / 1e6
    print(f"\nOK · {len(vectores)} vectores de {dim} dims → {VECTORES} ({mb:.1f} MB)")
    print(f"Meta → {META}")
    return meta


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(130)
