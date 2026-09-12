#!/usr/bin/env bash
# ============================================================
# Demo pública del portal (frontend + backend) mediante túneles.
# ============================================================
# Uso:
#   ./scripts/demo_tunel.sh
#
# Levanta:
#   - Weaviate (docker compose)
#   - API FastAPI en :8000
#   - Frontend compilado en :4173
#   - Un túnel Cloudflare para cada uno
#
# Al final imprime la URL con la que abrir el portal ya conectado al backend.
# Requiere: docker, cloudflared (en tools/ o en el PATH) y el build del frontend.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH=".pylibs:."
export HF_HOME="${HF_HOME:-/home/upta/DeepSeekHarness/upta/.rag-cache/hf}"

CF="$(command -v cloudflared || echo "../tools/cloudflared")"
[ -x "$CF" ] || { echo "ERROR: no encuentro cloudflared"; exit 1; }

echo "[1/5] Motor vectorial…"
docker compose up -d

echo "[2/5] Compilando el frontend…"
( cd web && npm install --silent && npm run build )

echo "[3/5] API en :8000…"
( uvicorn src.api:app --host 127.0.0.1 --port 8000 > /tmp/api.log 2>&1 & )
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/health >/dev/null && break; sleep 2; done

echo "[4/5] Sirviendo el frontend en :4173…"
( cd web/dist && python3 -m http.server 4173 --bind 127.0.0.1 > /tmp/web.log 2>&1 & )

echo "[5/5] Abriendo túneles…"
"$CF" tunnel --url http://127.0.0.1:8000 --no-autoupdate > /tmp/tunel-api.log 2>&1 &
"$CF" tunnel --url http://127.0.0.1:4173 --no-autoupdate > /tmp/tunel-web.log 2>&1 &

extraer() {
  for _ in $(seq 1 40); do
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$1" 2>/dev/null | head -1 || true)
    if [ -n "$url" ]; then echo "$url"; return 0; fi
    sleep 2
  done
  echo ""
}

API_URL=$(extraer /tmp/tunel-api.log)
WEB_URL=$(extraer /tmp/tunel-web.log)

echo
echo "================================================================"
echo "  Backend : ${API_URL:-'(no disponible)'}"
echo "  Portal  : ${WEB_URL:-'(no disponible)'}"
echo
echo "  Abre el portal conectado al backend:"
echo "  ${WEB_URL}/?api=${API_URL}"
echo "================================================================"
