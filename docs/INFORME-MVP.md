# Informe de ejecución del MVP — dominio jurídico

**Plataforma de Conocimiento Vectorial del BCV**
Repositorio: `bcv-conocimiento-vectorial`

Este informe documenta la ejecución **real** del MVP sobre el dominio
**jurídico-normativo** del BCV, fase por fase, con los resultados obtenidos.

---

## 1. Resumen

| Métrica | Valor |
|---|---|
| Páginas HTML ingeridas | 60 |
| Documentos descargados (PDF/Excel) | 165 |
| Documentos con texto extraído | 202 |
| Documentos descartados (escaneados sin OCR) | 19 |
| Chunks generados | 2 116 |
| Objetos indexados en Weaviate (únicos) | **2 050** |
| Modelo de embeddings | `BAAI/bge-m3` (1024 dim) |
| Modelo NER | `urchade/gliner_multi-v2.1` |
| Motor vectorial | Weaviate 1.28.4 |

---

## 2. Ejecución por fases

### F0 — Esqueleto del repositorio
Estructura modular (`config/`, `src/`, `scripts/`, `tests/`, `docs/`),
`docker-compose.yml` para Weaviate, `requirements.txt` y `Makefile`.

### F1 — Weaviate y esquema `Normativa`
- Colección con `vectorizer: none` (los vectores los aporta BGE-M3).
- Índice **HNSW**: `ef=128`, `efConstruction=256`, `maxConnections=32`,
  `dynamicEfFactor=2`, distancia coseno.
- Índice invertido **BM25** (`k1=1.2`, `b=0.75`) para la búsqueda por palabras clave.
- 14 propiedades, incluidas las de filtrado: `tipo_norma`, `materia`,
  `fecha_publicacion`, `entidades`.

### F2 — Ingesta del corpus jurídico
Secciones rastreadas: `/marco/leyes_bcv`, `/marco/convenios-cambiarios`,
resoluciones cambiaria/monetaria/pago/minerales, actos administrativos del
sistema de pagos, `SLBTR`, `SICET`, `CCE`, tarifario bancario.

**Resultado:** 60 páginas + 165 documentos (147 PDF, 14 XLSX, 4 XLS), 0 errores.

### F3 — Extracción multi-formato
HTML (con eliminación de menús/sidebars del portal Drupal), PDF (`pypdf`),
Word (`python-docx`) y Excel (`pandas`/`xlrd`/`openpyxl`).
Deduplicación por hash. **202 documentos con texto · 19 vacíos (escaneados).**

### F4 — Chunking estructural
Detección de `TÍTULO`/`CAPÍTULO`/`SECCIÓN`/`Artículo N` y corte por artículo,
con subdivisión con solape para bloques largos y respaldo por tamaño.

**2 116 chunks** · 925 estructurales · tamaño máximo 1 800 caracteres.

### F5 — NER con GLiNER
8 etiquetas de dominio, aplicadas en ingesta.

**1 923 / 2 116 chunks con entidades.** Distribución:

| Entidad | Menciones |
|---|---|
| institución | 3 991 |
| instrumento financiero | 1 475 |
| moneda | 1 309 |
| sistema de pago | 915 |
| periodo | 161 |
| indicador económico | 100 |
| tipo de norma | 45 |
| materia cambiaria | 24 |

### F6/F7 — Embeddings e indexado
BGE-M3 (L2-normalizado; consultas con prefijo de instrucción) e indexado por
lotes con **deduplicación por hash**. **2 050 objetos** indexados
(66 duplicados omitidos). El proceso es **reanudable**: si se interrumpe,
continúa donde quedó.

### F8 — Estrategias de búsqueda
Semántica, keyword (BM25), híbrida (`alpha` ajustable), re-ranking
(cross-encoder `BAAI/bge-reranker-v2-m3`) y filtros por metadatos.

### F9 — Evaluación

Conjunto *silver* de 40 consultas derivadas del corpus (auto-recuperación).
Métricas con documentos únicos (un documento cuenta una vez, aunque aporte
varios chunks). Top-k = 5:

| Estrategia | recall@5 | precision@5 | MRR | nDCG@5 |
|---|---|---|---|---|
| semántica | 0.650 | 0.130 | 0.481 | 0.524 |
| **keyword (BM25)** | **0.900** | **0.180** | **0.851** | **0.863** |
| híbrida (α=0.5) | 0.875 | 0.175 | 0.833 | 0.844 |
| híbrida (α=0.7) | 0.750 | 0.150 | 0.635 | 0.665 |
| híbrida + re-ranking | 0.900 | 0.180 | 0.823 | 0.842 |

**Mejor estrategia: keyword (nDCG@5 = 0.863).**

> **Lectura crítica.** El conjunto de evaluación se deriva de términos del
> propio corpus, lo que **favorece la coincidencia léxica** (BM25). Con juicios
> de relevancia humanos —o consultas parafraseadas— se espera que la búsqueda
> semántica e híbrida mejoren respecto de este *baseline*. Es una limitación
> metodológica conocida del MVP, no un defecto del motor.

### F10 — API
FastAPI con `/health`, `/stats`, `/schema`, `POST /search` y `GET /search`
(más filtros). Verificado en local: 2 050 objetos y resultados filtrados
correctos por `materia=Cambiario`.

---

## 3. Pruebas

`pytest` — 6 pruebas: chunking estructural, límite de tamaño, NER por reglas,
métricas de recuperación y ausencia de inflado por duplicados.

---

## 4. Limitaciones y siguientes pasos

| Limitación | Siguiente paso |
|---|---|
| 19 PDF escaneados sin texto | Añadir OCR (Tesseract) al pipeline de extracción. |
| Evaluación *silver* (sin juicios humanos) | Construir un set etiquetado por el BCV (positivas/negativas). |
| Dominio único (jurídico) | Extender a monetario, estadístico, pagos, institucional. |
| Datos volátiles no embebidos | Mantener el canal estructurado aparte (tipo de cambio/tasas). |
| Re-ranking con cross-encoder | Evaluar ColBERT (late interaction) y ajustar `alpha` y HNSW `ef`. |
