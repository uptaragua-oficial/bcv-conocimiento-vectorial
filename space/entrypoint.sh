#!/usr/bin/env bash
# ============================================================
# Arranque del Space: Weaviate (binario) + API FastAPI
# ============================================================
set -euo pipefail

WV_PORT="${WEAVIATE_HTTP_PORT:-8080}"
API_PORT="${PORT:-7860}"
DATA_PATH="${PERSISTENCE_DATA_PATH:-/tmp/weaviate-data}"

# --- Configuración de Weaviate ---
export PERSISTENCE_DATA_PATH="${DATA_PATH}"
export DEFAULT_VECTORIZER_MODULE="none"
export AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED="true"
export AUTHENTICATION_APIKEY_ENABLED="false"
export QUERY_DEFAULTS_LIMIT="25"
export CLUSTER_HOSTNAME="node1"
export ENABLE_MODULES=""
export LOG_LEVEL="info"
mkdir -p "${DATA_PATH}"

echo "[space] arrancando Weaviate en :${WV_PORT} (datos en ${DATA_PATH})"
weaviate --host 0.0.0.0 --port "${WV_PORT}" --scheme http &
WV_PID=$!
trap 'echo "[space] deteniendo Weaviate"; kill "${WV_PID}" 2>/dev/null || true' EXIT

echo "[space] esperando disponibilidad de Weaviate…"
LISTO=""
for i in $(seq 1 90); do
  if curl -sf "http://localhost:${WV_PORT}/v1/.well-known/ready" >/dev/null 2>&1; then
    echo "[space] Weaviate listo tras $((i * 2))s"
    LISTO="si"
    break
  fi
  sleep 2
done
if [ -z "${LISTO}" ]; then
  echo "[space] ERROR: Weaviate no respondió a tiempo"
  exit 1
fi

cd /app
echo "[space] importando el índice vectorial precomputado…"
if ! python /app/space/import_index.py; then
  echo "[space] AVISO: la importación falló; la API arrancará igualmente"
fi

echo "[space] iniciando la API en :${API_PORT}"
exec uvicorn src.api:app --host 0.0.0.0 --port "${API_PORT}" --workers 1
