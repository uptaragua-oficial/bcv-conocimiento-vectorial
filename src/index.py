"""F7 — Indexado en Weaviate: BM25 (invertido) + vectores densos + HNSW.

Toma ``data/processed/chunks_ner.jsonl``, calcula los embeddings con BGE-M3 y
carga los objetos en la colección ``Normativa``.

Notas de diseño:
  * El índice invertido (BM25) lo construye Weaviate automáticamente con las
    propiedades de texto → habilita *keyword search*.
  * Los vectores densos alimentan el índice **HNSW** → *semantic search*.
  * La combinación de ambos es la base de la *búsqueda híbrida*.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from config import settings
from src import embeddings, store

RE_FECHA = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")


def _fecha_iso(texto: str) -> str | None:
    m = RE_FECHA.search(texto or "")
    if not m:
        return None
    d, mes, a = (int(g) for g in m.groups())
    try:
        return datetime(a, mes, d).strftime("%Y-%m-%dT00:00:00Z")
    except ValueError:
        return None


def _propiedades(c: dict) -> dict:
    props = {
        "doc_id": c.get("doc_id") or "",
        "titulo": (c.get("titulo") or "")[:900],
        "texto": c.get("texto") or "",
        "fuente_url": c.get("fuente_url") or "",
        "tipo_norma": c.get("tipo_norma") or "No especificado",
        "materia": c.get("materia") or "General",
        "entidades": c.get("entidades") or [],
        "seccion": (c.get("seccion") or "")[:300],
        "chunk_index": int(c.get("chunk_index") or 0),
        "doc_hash": c.get("doc_hash") or "",
        "n_caracteres": int(c.get("n_caracteres") or 0),
        "vigencia": c.get("vigencia") or "desconocida",
    }
    fecha = _fecha_iso(c.get("texto", ""))
    if fecha:
        props["fecha_publicacion"] = fecha
    return props


def load_chunks() -> list[dict]:
    path = settings.PROCESSED_DIR / "chunks_ner.jsonl"
    if not path.exists():
        raise SystemExit("No hay chunks_ner.jsonl. Ejecuta primero: python -m src.ner")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def run(recreate: bool = False, embed_batch: int = 16) -> dict:
    chunks = load_chunks()
    print(f"Indexando {len(chunks)} chunks en Weaviate (colección "
          f"'{settings.WEAVIATE_COLLECTION}')...\n")

    if not store.is_ready():
        raise SystemExit(
            "Weaviate no responde. Levántalo con: docker compose up -d"
        )

    insertados = 0
    with store.collection(recreate=recreate) as (_client, col):
        if recreate:
            print("Colección recreada (vaciada).")

        for i in range(0, len(chunks), embed_batch):
            lote = chunks[i : i + embed_batch]
            vectores = embeddings.embed_documents([c["texto"] for c in lote])
            with col.batch.dynamic() as batch:
                for c, vec in zip(lote, vectores):
                    batch.add_object(properties=_propiedades(c), vector=vec)
            insertados += len(lote)
            print(f"  indexados {insertados}/{len(chunks)}")

        total = store.count_objects(col)

    print(f"\nResumen indexado: {insertados} objetos enviados · {total} en la colección")
    return {"insertados": insertados, "total": total}


def reset() -> None:
    """Elimina y recrea la colección vacía."""
    with store.collection(recreate=True):
        pass
    print(f"Colección '{settings.WEAVIATE_COLLECTION}' recreada vacía.")


if __name__ == "__main__":
    import sys

    if "--reset" in sys.argv:
        reset()
    else:
        run(recreate="--recreate" in sys.argv)
