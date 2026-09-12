"""Configuración central del MVP (lee variables de entorno con valores por defecto).

Todas las rutas son relativas a la raíz del proyecto para que el pipeline
funcione igual en local y en CI.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Carga .env si existe (sin dependencia dura de python-dotenv) ---
ROOT = Path(__file__).resolve().parent.parent
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        os.environ.setdefault(_k.strip(), _v.strip())


def _b(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ---------------- Rutas ----------------
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"            # artefactos originales descargados
PROCESSED_DIR = DATA_DIR / "processed"  # chunking + NER
INDEX_DIR = DATA_DIR / "index"        # evaluación, logs
DOCS_DIR = ROOT / "docs"
LEGAL_DIR = DOCS_DIR / "legal"        # corpus jurídico (HTML/PDF)

for _d in (RAW_DIR, PROCESSED_DIR, INDEX_DIR, LEGAL_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------- Weaviate ----------------
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_HTTP_PORT = _i("WEAVIATE_HTTP_PORT", 8081)
WEAVIATE_GRPC_PORT = _i("WEAVIATE_GRPC_PORT", 50052)
WEAVIATE_COLLECTION = os.getenv("WEAVIATE_COLLECTION", "Normativa")

# ---------------- Modelos ----------------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = _i("EMBEDDING_DIM", 1024)
NER_MODEL = os.getenv("NER_MODEL", "urchade/gliner_multi-v2.1")
NER_ENABLED = _b("NER_ENABLED", True)
NER_THRESHOLD = _f("NER_THRESHOLD", 0.4)

# ---------------- HNSW ----------------
HNSW_EF_CONSTRUCTION = _i("HNSW_EF_CONSTRUCTION", 256)
HNSW_MAX_CONNECTIONS = _i("HNSW_MAX_CONNECTIONS", 32)
HNSW_EF = _i("HNSW_EF", 128)
HNSW_DYNAMIC_EF_FACTOR = _i("HNSW_DYNAMIC_EF_FACTOR", 2)

# ---------------- Ingesta ----------------
BCV_BASE_URL = os.getenv("BCV_BASE_URL", "https://www.bcv.org.ve")
USER_AGENT = os.getenv(
    "USER_AGENT",
    "BCV-VectorKnowledge-MVP/0.1 (asesoria tecnica; contacto: universidadfbf@gmail.com)",
)
REQUEST_DELAY_SECONDS = _f("REQUEST_DELAY_SECONDS", 1.0)
VERIFY_SSL = _b("VERIFY_SSL", False)

# ---------------- Chunking ----------------
CHUNK_MAX_CHARS = _i("CHUNK_MAX_CHARS", 1800)
CHUNK_MIN_CHARS = _i("CHUNK_MIN_CHARS", 120)
CHUNK_OVERLAP_CHARS = _i("CHUNK_OVERLAP_CHARS", 200)

# ---------------- Entidades del dominio jurídico (para NER) ----------------
LEGAL_ENTITY_LABELS = [
    "moneda",
    "instrumento_financiero",
    "sistema_de_pago",
    "tipo_de_norma",
    "institucion",
    "indicador_economico",
    "periodo",
    "materia_cambiaria",
]
