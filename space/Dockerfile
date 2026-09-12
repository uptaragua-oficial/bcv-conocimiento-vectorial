# ============================================================
# HuggingFace Space — backend de consulta normativa del BCV
# ============================================================
# Contenedor único que ejecuta:
#   1. Weaviate (binario) con el índice jurídico precomputado.
#   2. La API FastAPI (búsqueda + asistente RAG) en el puerto 7860.
#
# El código (src/, config/) se toma del repositorio de GitHub para
# mantener una única fuente de verdad. El índice vectorial ya calculado
# viaja en data/ para que el arranque sea rápido (sin re-embeder).
# ============================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/data/hf \
    PORT=7860 \
    WEAVIATE_HOST=localhost \
    WEAVIATE_HTTP_PORT=8080 \
    WEAVIATE_GRPC_PORT=50051 \
    NER_ENABLED=false

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# --- Código del proyecto (fuente única: GitHub) ---
ARG REPO_URL=https://github.com/uptaragua-oficial/bcv-conocimiento-vectorial
ARG REPO_REF=main
RUN git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" /tmp/repo \
 && cp -r /tmp/repo/src /tmp/repo/config /app/ \
 && rm -rf /tmp/repo

# --- Dependencias de Python (runtime, sin dev) ---
COPY requirements.txt /app/space/requirements.txt
RUN pip install --no-cache-dir -r /app/space/requirements.txt

# --- Motor vectorial (binario, sin Docker anidado) ---
RUN curl -fsSL https://github.com/weaviate/weaviate/releases/download/v1.28.4/weaviate-v1.28.4-linux-amd64.tar.gz \
      -o /tmp/weaviate.tgz \
 && tar -xzf /tmp/weaviate.tgz -C /usr/local/bin weaviate \
 && chmod +x /usr/local/bin/weaviate \
 && rm -f /tmp/weaviate.tgz

# --- Índice vectorial precomputado + scripts de arranque ---
COPY data /app/space/data
COPY import_index.py entrypoint.sh /app/space/
RUN chmod +x /app/space/entrypoint.sh

EXPOSE 7860

CMD ["bash", "/app/space/entrypoint.sh"]
