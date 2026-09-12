"""F10 — API de consulta (FastAPI) sobre la colección `Normativa`.

Expone el motor de recuperación para que sea consumible por agentes de IA y
otras soluciones, tal como plantea la propuesta.

Endpoints:
  GET  /health          → estado del servicio y de Weaviate
  GET  /stats           → número de objetos y configuración del índice
  GET  /schema          → esquema de la colección
  POST /search          → búsqueda (semantic | keyword | hybrid) con filtros
  GET  /search          → variante GET para pruebas rápidas

Ejecución:
  uvicorn src.api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from config import settings
from src import search as search_mod
from src import store

app = FastAPI(
    title="BCV · Plataforma de Conocimiento Vectorial (MVP jurídico)",
    description=(
        "API de recuperación sobre el corpus jurídico-normativo del BCV. "
        "Estrategias: búsqueda semántica (BGE-M3 + HNSW), keyword (BM25) e "
        "híbrida, con filtros por tipo de norma, materia y entidades."
    ),
    version="0.1.0",
)


class SearchRequest(BaseModel):
    query: str = Field(..., description="Consulta en lenguaje natural.")
    modo: str = Field("hybrid", description="semantic | keyword | hybrid")
    limit: int = Field(5, ge=1, le=50)
    alpha: float = Field(0.5, ge=0.0, le=1.0, description="Peso denso vs. léxico (híbrida).")
    rerank: bool = Field(False, description="Aplicar re-ranking (cross-encoder si está disponible).")
    filtros: dict[str, Any] | None = Field(
        None,
        description="Filtros: tipo_norma, materia, doc_id, entidades[], fecha_desde, fecha_hasta.",
        examples=[{"materia": "Cambiario", "tipo_norma": "Resolución"}],
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "weaviate": store.is_ready(),
        "collection": settings.WEAVIATE_COLLECTION,
        "embedding_model": settings.EMBEDDING_MODEL,
    }


@app.get("/stats")
def stats():
    try:
        with store.collection() as (_c, col):
            total = store.count_objects(col)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Weaviate no disponible: {exc}") from exc
    return {
        "coleccion": settings.WEAVIATE_COLLECTION,
        "objetos": total,
        "embedding_model": settings.EMBEDDING_MODEL,
        "hnsw": {
            "ef": settings.HNSW_EF,
            "efConstruction": settings.HNSW_EF_CONSTRUCTION,
            "maxConnections": settings.HNSW_MAX_CONNECTIONS,
        },
    }


@app.get("/schema")
def schema():
    from src.schema import schema_dict

    return schema_dict()


@app.post("/search")
def search_post(req: SearchRequest):
    if req.modo not in ("semantic", "keyword", "hybrid"):
        raise HTTPException(status_code=400, detail="modo debe ser semantic | keyword | hybrid")
    try:
        resultados = search_mod.search(
            req.query, modo=req.modo, limit=req.limit, alpha=req.alpha,
            filtros=req.filtros, rerank=req.rerank,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Error de búsqueda: {exc}") from exc
    return {"query": req.query, "modo": req.modo, "n": len(resultados), "resultados": resultados}


@app.get("/search")
def search_get(
    q: str = Query(..., description="Consulta"),
    modo: str = Query("hybrid"),
    limit: int = Query(5, ge=1, le=50),
    alpha: float = Query(0.5, ge=0.0, le=1.0),
    rerank: bool = Query(False),
    tipo_norma: str | None = Query(None),
    materia: str | None = Query(None),
):
    filtros = {k: v for k, v in {"tipo_norma": tipo_norma, "materia": materia}.items() if v}
    return search_post(SearchRequest(
        query=q, modo=modo, limit=limit, alpha=alpha, rerank=rerank, filtros=filtros or None
    ))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
