# BCV · Plataforma de Conocimiento Vectorial — MVP (dominio jurídico)

Implementación del **MVP** de la propuesta *Plataforma de Conocimiento Vectorial
del Banco Central de Venezuela*, aplicada a un dominio específico: el
**corpus jurídico-normativo** del BCV.

El objetivo es construir, de punta a punta, las **bases de datos vectoriales**
que hagan el corpus jurídico consultable de forma **semántica, por palabras
clave e híbrida**, y **consumible por agentes de IA** mediante una API.

---

## 1. Arquitectura

```
FUENTES JURÍDICAS DEL BCV (marco legal, convenios, resoluciones, actos administrativos)
        │  F2 ingesta
        ▼
PIPELINE DE PREPARACIÓN
  F3 extracción (HTML/PDF/Word/Excel) → F4 chunking estructural → F5 NER (GLiNER)
        │
        ▼
WEAVIATE  (colección `Normativa`)
  Keyword (BM25) · Dense (BGE-M3) · HNSW (ANN)
        │
        ▼
CAPA DE BÚSQUEDA (F8)
  semántica · keyword · híbrida · re-ranking · filtros
        │
        ▼
EVALUACIÓN (F9) · API (F10) → agentes de IA y otras soluciones
```

| Componente | Tecnología |
|---|---|
| Motor vectorial | Weaviate 1.28 (`vectorizer: none`) |
| Embeddings densos | `BAAI/bge-m3` (1024 dim, L2-normalizado) |
| Keyword / sparse | BM25 nativo de Weaviate |
| Índice ANN | HNSW (`ef`, `efConstruction`, `maxConnections`) |
| Re-ranking | Cross-encoder `BAAI/bge-reranker-v2-m3` (opcional) |
| NER | GLiNER `urchade/gliner_multi-v2.1` (+ respaldo por reglas) |
| API | FastAPI |

---

## 2. Fases del MVP

| Fase | Módulo | Descripción |
|---|---|---|
| **F0** | estructura | Esqueleto del repositorio. |
| **F1** | `src/schema.py` | Esquema de la colección `Normativa` e índice HNSW. |
| **F2** | `src/ingest.py` | Ingesta y preservación de fuentes jurídicas (HTML + documentos). |
| **F3** | `src/extract.py` | Extracción multi-formato (HTML, PDF, Word, Excel). |
| **F4** | `src/chunking.py` | Chunking estructural por artículo (+ respaldo por tamaño). |
| **F5** | `src/ner.py` | Reconocimiento de entidades (GLiNER / reglas). |
| **F6** | `src/embeddings.py` | Embeddings densos con BGE-M3. |
| **F7** | `src/index.py` | Indexado: BM25 + vectores densos + HNSW. |
| **F8** | `src/search.py` | Estrategias de búsqueda y filtros. |
| **F9** | `src/evaluate.py` | Evaluación (recall@k, MRR, nDCG) y logging. |
| **F10** | `src/api.py` | API FastAPI de consulta. |

---

## 3. Requisitos

- Docker + Docker Compose
- Python 3.12

## 4. Instalación

```bash
# 1) Motor vectorial
docker compose up -d

# 2) Dependencias de Python (en .pylibs, sin venv por restricciones del FS)
pip install --target .pylibs --index-url https://download.pytorch.org/whl/cpu torch
pip install --target .pylibs -r requirements.txt

# 3) Configuración
cp .env.example .env
```

Para ejecutar cualquier módulo:

```bash
export PYTHONPATH=.pylibs:.
python -m src.<modulo>
```

---

## 5. Ejecución del pipeline

```bash
python -m src.ingest      # F2 · descarga el corpus jurídico
python -m src.extract     # F3 · extrae texto multi-formato
python -m src.chunking    # F4 · fragmenta por artículo
python -m src.ner         # F5 · entidades
python -m src.index --recreate   # F6+F7 · embeddings e indexado
python -m src.evaluate    # F9 · métricas de recuperación
uvicorn src.api:app --port 8000  # F10 · API
```

Atajos: `make setup | make pipeline | make api`.

---

## 6. API

```bash
curl -s localhost:8000/health

curl -s -X POST localhost:8000/search -H 'Content-Type: application/json' -d '{
  "query": "requisitos para operar como operador cambiario",
  "modo": "hybrid",
  "limit": 5,
  "filtros": {"materia": "Cambiario"}
}'
```

---

## 7. Resultados

Ejecución real del MVP sobre el dominio jurídico (ver
[`docs/INFORME-MVP.md`](docs/INFORME-MVP.md) para el detalle):

| Etapa | Resultado |
|---|---|
| Ingesta | 60 páginas + 165 documentos (PDF/Excel) |
| Extracción | 202 documentos con texto (19 escaneados sin OCR) |
| Chunking | 2 116 chunks (925 estructurales por artículo) |
| NER (GLiNER) | 1 923 chunks con entidades |
| Indexado | **2 050 objetos** en Weaviate |

Evaluación (40 consultas, top-5):

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---|---|---|
| semántica | 0.650 | 0.481 | 0.524 |
| **keyword (BM25)** | **0.900** | **0.851** | **0.863** |
| híbrida (α=0.5) | 0.875 | 0.833 | 0.844 |
| híbrida + re-ranking | 0.900 | 0.823 | 0.842 |

Artefactos: `data/index/evaluation_report.json` (métricas) y
`data/index/queries.jsonl` (log de consultas).

---

## 8. Alcance y límites del MVP

- Dominio único: **jurídico-normativo** (el resto de dominios queda para fases
  posteriores, según la propuesta).
- Conjunto de evaluación *silver* por auto-recuperación (sin juicios humanos).
- Despliegue local; Weaviate en Docker, sin autenticación.
