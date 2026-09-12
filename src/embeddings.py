"""F6 — Embeddings densos con BGE-M3 (bi-encoder).

- Modelo por defecto: ``BAAI/bge-m3`` (multilingüe, 1024 dim).
- Normalización L2 (similitud coseno), coherente con el índice HNSW.
- Uso asimétrico: los documentos se embeben sin prefijo; las consultas se
  embeben con un prefijo de instrucción (mejora el *recall* en recuperación).

Se reutiliza el cache local de HuggingFace si existe, para no re-descargar.
"""
from __future__ import annotations

import os
from pathlib import Path

from config import settings

# Reutilizar cache local de modelos si está disponible.
_CACHE_CANDIDATOS = [
    Path("/home/upta/DeepSeekHarness/upta/.rag-cache/hf"),
    Path.home() / ".cache" / "huggingface",
]
for _c in _CACHE_CANDIDATOS:
    if _c.exists():
        os.environ.setdefault("HF_HOME", str(_c))
        break

# Prefijo de instrucción para consultas (BGE-M3).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None


def get_model():
    """Carga (una sola vez) el modelo de embeddings."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        print(f"Cargando modelo de embeddings: {settings.EMBEDDING_MODEL} ...")
        _model = SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")
    return _model


def embed_documents(textos: list[str], batch_size: int = 8) -> list[list[float]]:
    """Embebe documentos (sin prefijo)."""
    model = get_model()
    vecs = model.encode(
        textos, batch_size=batch_size, normalize_embeddings=True,
        show_progress_bar=len(textos) > 20, convert_to_numpy=True,
    )
    return [v.tolist() for v in vecs]


def embed_query(texto: str) -> list[float]:
    """Embebe una consulta (con prefijo de instrucción)."""
    model = get_model()
    v = model.encode([QUERY_PREFIX + texto], normalize_embeddings=True, convert_to_numpy=True)
    return v[0].tolist()


def dimension() -> int:
    """Dimensión real del modelo (para validar el esquema)."""
    return len(embed_query("prueba"))


def selftest() -> None:
    vecs = embed_documents(["El Banco Central de Venezuela fija el tipo de cambio oficial."])
    vq = embed_query("tipo de cambio oficial")
    import math

    sim = sum(a * b for a, b in zip(vecs[0], vq))
    print(f"OK · dim={len(vecs[0])} · similitud(coseno)={sim:.4f}")


if __name__ == "__main__":
    selftest()
