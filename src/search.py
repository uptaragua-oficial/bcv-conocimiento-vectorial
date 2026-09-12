"""F8 — Estrategias de búsqueda sobre la colección `Normativa`.

Implementa las cinco estrategias de la propuesta:

  * ``semantic``  → vectores densos (BGE-M3) sobre índice HNSW.
  * ``keyword``   → BM25 sobre el índice invertido.
  * ``hybrid``    → fusión densa+léxica con parámetro ``alpha``.
  * ``rerank``    → re-ordenación del top-k con cross-encoder (si está
                    disponible) o con fusión de scores como respaldo.
  * ``filters``   → restricción por ``tipo_norma``, ``materia``, ``entidades``
                    y rango de fechas (cláusula ``where``).

Todas las consultas se registran en ``data/index/queries.jsonl`` (logging),
lo que alimenta la fase de evaluación y monitoreo.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from config import settings
from src import embeddings, store

# ----------------------------------------------------------------------
# Filtros
# ----------------------------------------------------------------------
def build_filter(filtros: dict[str, Any] | None):
    """Construye un ``Filter`` de Weaviate a partir de un diccionario."""
    if not filtros:
        return None
    from weaviate.classes.query import Filter

    f = None

    def _combinar(actual, nuevo):
        return nuevo if actual is None else actual & nuevo

    if filtros.get("tipo_norma"):
        f = _combinar(f, Filter.by_property("tipo_norma").equal(filtros["tipo_norma"]))
    if filtros.get("materia"):
        f = _combinar(f, Filter.by_property("materia").equal(filtros["materia"]))
    if filtros.get("doc_id"):
        f = _combinar(f, Filter.by_property("doc_id").equal(filtros["doc_id"]))
    if filtros.get("entidades"):
        ents = filtros["entidades"]
        ents = ents if isinstance(ents, list) else [ents]
        f = _combinar(f, Filter.by_property("entidades").contains_any(ents))
    if filtros.get("fecha_desde"):
        f = _combinar(
            f, Filter.by_property("fecha_publicacion").greater_or_equal(filtros["fecha_desde"])
        )
    if filtros.get("fecha_hasta"):
        f = _combinar(
            f, Filter.by_property("fecha_publicacion").less_or_equal(filtros["fecha_hasta"])
        )
    return f


# ----------------------------------------------------------------------
# Re-ranking
# ----------------------------------------------------------------------
_reranker = None
_reranker_intentado = False


def _get_reranker():
    """Carga un cross-encoder si está disponible (opcional)."""
    global _reranker, _reranker_intentado
    if _reranker_intentado:
        return _reranker
    _reranker_intentado = True
    try:
        from sentence_transformers import CrossEncoder

        nombre = "BAAI/bge-reranker-v2-m3"
        print(f"Cargando cross-encoder: {nombre} ...")
        _reranker = CrossEncoder(nombre, device="cpu")
    except Exception as exc:  # noqa: BLE001
        print(f"[aviso] Cross-encoder no disponible ({exc}). Re-ranking por fusión de scores.")
        _reranker = None
    return _reranker


def _rerank(query: str, items: list[dict], top_k: int) -> list[dict]:
    if not items:
        return items
    ce = _get_reranker()
    if ce is not None:
        try:
            pares = [(query, it["texto"]) for it in items]
            scores = ce.predict(pares)
            for it, s in zip(items, scores):
                it["rerank_score"] = float(s)
            items.sort(key=lambda x: x["rerank_score"], reverse=True)
            return items[:top_k]
        except Exception:  # noqa: BLE001
            pass
    # Respaldo: normalizar y combinar score nativo (si existe)
    for it in items:
        it["rerank_score"] = float(it.get("score") or 0.0)
    items.sort(key=lambda x: x["rerank_score"], reverse=True)
    return items[:top_k]


# ----------------------------------------------------------------------
# Búsquedas
# ----------------------------------------------------------------------
def _fila(obj) -> dict:
    p = obj.properties
    meta = getattr(obj, "metadata", None)
    score = getattr(meta, "score", None)
    distance = getattr(meta, "distance", None)
    # En near_vector Weaviate devuelve distancia (coseno); la convertimos a
    # similitud para que el score sea comparable entre estrategias.
    if distance is not None and (score is None or float(score) == 0.0):
        score = 1.0 - float(distance)
    return {
        "uuid": str(obj.uuid),
        "doc_id": p.get("doc_id"),
        "titulo": p.get("titulo"),
        "seccion": p.get("seccion"),
        "tipo_norma": p.get("tipo_norma"),
        "materia": p.get("materia"),
        "fuente_url": p.get("fuente_url"),
        "entidades": p.get("entidades") or [],
        "texto": p.get("texto"),
        "score": score,
        "distance": distance,
    }


def _consultar(modo: str, query: str, limit: int, alpha: float, filtros: dict | None):
    from weaviate.classes.query import MetadataQuery

    f = build_filter(filtros)
    meta = MetadataQuery(score=True, distance=True)
    with store.collection() as (_c, col):
        if modo == "semantic":
            vec = embeddings.embed_query(query)
            res = col.query.near_vector(
                near_vector=vec, limit=limit, filters=f, return_metadata=meta
            )
        elif modo == "keyword":
            res = col.query.bm25(query=query, limit=limit, filters=f, return_metadata=meta)
        elif modo == "hybrid":
            vec = embeddings.embed_query(query)
            res = col.query.hybrid(
                query=query, vector=vec, alpha=alpha, limit=limit,
                filters=f, return_metadata=meta,
            )
        else:
            raise ValueError(f"Modo desconocido: {modo}")
        return [_fila(o) for o in res.objects]


def search(
    query: str,
    modo: str = "hybrid",
    limit: int = 5,
    alpha: float = 0.5,
    filtros: dict | None = None,
    rerank: bool = False,
    log: bool = True,
) -> list[dict]:
    """Búsqueda unificada. ``modo`` ∈ {semantic, keyword, hybrid}."""
    t0 = time.perf_counter()
    candidatos = _consultar(modo, query, max(limit * 4, 20) if rerank else limit, alpha, filtros)
    if rerank:
        candidatos = _rerank(query, candidatos, limit)
    else:
        candidatos = candidatos[:limit]
    ms = (time.perf_counter() - t0) * 1000

    if log:
        _log_query(query, modo, limit, alpha, filtros, rerank, len(candidatos), ms)
    return candidatos


def _log_query(query, modo, limit, alpha, filtros, rerank, n, ms) -> None:
    ruta = settings.INDEX_DIR / "queries.jsonl"
    registro = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query": query, "modo": modo, "limit": limit, "alpha": alpha,
        "filtros": filtros, "rerank": rerank, "n_resultados": n,
        "latencia_ms": round(ms, 2),
    }
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "tipo de cambio oficial"
    for m in ("semantic", "keyword", "hybrid"):
        print(f"\n=== {m.upper()} :: {q} ===")
        for r in search(q, modo=m, limit=3, rerank=True):
            print(f"  [{r['score']:.3f}] {r['seccion'][:50]:<50} {r['texto'][:70]}...")
