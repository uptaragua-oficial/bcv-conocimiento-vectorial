"""Exporta el índice vectorial a archivos portables (para el HuggingFace Space).

Genera en ``space/data/``:
  * ``objects.jsonl`` — propiedades de cada objeto (sin vector).
  * ``vectors.npy``   — matriz float32 (N × 1024) con los vectores densos.

Así el Space arranca en segundos: no re-embebe el corpus, solo carga los
vectores ya calculados por BGE-M3.

Uso:
  python -m scripts.export_index
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from config import settings
from src import store


def _serializar(o):
    """Serializa fechas en RFC3339 (requisito del tipo DATE de Weaviate)."""
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


DESTINO = Path(__file__).resolve().parent.parent / "space" / "data"
CAMPOS = [
    "doc_id", "titulo", "texto", "fuente_url", "tipo_norma",
    "fecha_publicacion", "gaceta", "materia", "entidades", "seccion",
    "chunk_index", "doc_hash", "n_caracteres", "vigencia",
]


def _vector_de(obj) -> list[float] | None:
    v = obj.vector
    if v is None:
        return None
    if isinstance(v, dict):  # vectores con nombre
        return v.get("default") or next(iter(v.values()), None)
    return list(v)


def run() -> dict:
    DESTINO.mkdir(parents=True, exist_ok=True)
    objetos, vectores = [], []

    with store.collection() as (_c, col):
        for obj in col.iterator(include_vector=True, return_properties=CAMPOS):
            vec = _vector_de(obj)
            if not vec:
                continue
            props = {k: obj.properties.get(k) for k in CAMPOS}
            # Quitar nulos para no escribir basura
            props = {k: v for k, v in props.items() if v not in (None, "", [])}
            objetos.append(props)
            vectores.append(vec)

    if not objetos:
        raise SystemExit("No hay objetos que exportar. ¿Está indexado el corpus?")

    matriz = np.asarray(vectores, dtype=np.float32)
    np.save(DESTINO / "vectors.npy", matriz)
    with (DESTINO / "objects.jsonl").open("w", encoding="utf-8") as f:
        for o in objetos:
            f.write(json.dumps(o, ensure_ascii=False, default=_serializar) + "\n")

    meta = {
        "n_objetos": len(objetos),
        "dim": int(matriz.shape[1]),
        "embedding_model": settings.EMBEDDING_MODEL,
        "coleccion": settings.WEAVIATE_COLLECTION,
    }
    (DESTINO / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    mb = matriz.nbytes / 1e6
    print(f"Exportados {len(objetos)} objetos · dim={matriz.shape[1]} · vectores {mb:.1f} MB")
    print(f"Destino: {DESTINO}")
    return meta


if __name__ == "__main__":
    run()
