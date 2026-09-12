"""Esquema de la colección `Normativa` en Weaviate (dominio jurídico).

Diseño:
  * Un objeto = un *chunk* estructural de una norma (típicamente un artículo).
  * `vectorizer=none`: los vectores densos los aporta BGE-M3 (nosotros).
  * `vector_index_config` = HNSW con parámetros ajustables (ef, efConstruction,
    maxConnections, dynamicEfFactor), tal como plantea la propuesta.
  * Las propiedades de filtrado (`tipo_norma`, `fecha_publicacion`, `materia`,
    `entidades`) habilitan la búsqueda híbrida con cláusulas `where`.
"""
from __future__ import annotations

from config import settings

# (nombre, tipo lógico, descripción) — el tipo lógico se mapea al de Weaviate.
PROPERTIES: list[tuple[str, str, str]] = [
    ("doc_id", "text", "Identificador estable del documento de origen."),
    ("titulo", "text", "Título de la norma o documento."),
    ("texto", "text", "Texto del chunk (artículo/numeral)."),
    ("fuente_url", "text", "URL oficial de la fuente."),
    ("tipo_norma", "text", "Resolución, circular, convenio, aviso, ley, providencia."),
    ("fecha_publicacion", "date", "Fecha de publicación (ISO 8601)."),
    ("gaceta", "text", "Número / identificación de Gaceta Oficial, si aplica."),
    ("materia", "text", "Materia o dominio (cambiario, monetario, pagos, etc.)."),
    ("entidades", "text[]", "Entidades extraídas por NER (GLiNER)."),
    ("seccion", "text", "Etiqueta estructural: 'Artículo 5', 'Título II', etc."),
    ("chunk_index", "int", "Orden del chunk dentro del documento."),
    ("doc_hash", "text", "Hash del contenido del chunk (deduplicación)."),
    ("n_caracteres", "int", "Longitud del texto del chunk."),
    ("vigencia", "text", "Estado declarado: vigente / derogada / desconocida."),
]

DESCRIPTION = "Corpus jurídico-normativo del BCV (un objeto por chunk estructural)."


def schema_dict() -> dict:
    """Representación JSON del esquema (para documentación e inspección)."""
    return {
        "class": settings.WEAVIATE_COLLECTION,
        "description": DESCRIPTION,
        "vectorizer": "none",
        "vectorIndexConfig": {
            "distance": "cosine",
            "ef": settings.HNSW_EF,
            "efConstruction": settings.HNSW_EF_CONSTRUCTION,
            "maxConnections": settings.HNSW_MAX_CONNECTIONS,
            "dynamicEfFactor": settings.HNSW_DYNAMIC_EF_FACTOR,
        },
        "invertedIndexConfig": {"bm25": {"b": 0.75, "k1": 1.2}},
        "properties": [
            {"name": n, "dataType": t, "description": d} for n, t, d in PROPERTIES
        ],
    }


def create_collection(client, recreate: bool = False):
    """Crea la colección `Normativa` si no existe (o la recrea si ``recreate``)."""
    from weaviate.classes.config import (
        Configure,
        DataType,
        Property,
        VectorDistances,
    )

    name = settings.WEAVIATE_COLLECTION

    if recreate and client.collections.exists(name):
        client.collections.delete(name)

    if client.collections.exists(name):
        return client.collections.get(name)

    type_map = {
        "text": DataType.TEXT,
        "date": DataType.DATE,
        "int": DataType.INT,
        "text[]": DataType.TEXT_ARRAY,
    }
    properties = [
        Property(name=n, data_type=type_map[t], description=d)
        for n, t, d in PROPERTIES
    ]

    return client.collections.create(
        name=name,
        description=DESCRIPTION,
        vector_config=Configure.Vectors.self_provided(
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
                ef=settings.HNSW_EF,
                ef_construction=settings.HNSW_EF_CONSTRUCTION,
                max_connections=settings.HNSW_MAX_CONNECTIONS,
                dynamic_ef_factor=settings.HNSW_DYNAMIC_EF_FACTOR,
            ),
        ),
        inverted_index_config=Configure.inverted_index(
            bm25_b=0.75, bm25_k1=1.2, index_timestamps=False
        ),
        properties=properties,
    )


if __name__ == "__main__":
    import json

    print(json.dumps(schema_dict(), indent=2, ensure_ascii=False))
