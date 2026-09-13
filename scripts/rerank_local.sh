#!/usr/bin/env bash
# ============================================================
# Rerank local + túnel, listo para pegar en Vercel.
# ============================================================
# Ejecuta el cross-encoder en ESTA máquina (con GPU si la hay) y lo publica
# mediante un túnel de Cloudflare para que la función de Vercel pueda
# alcanzarlo. Evita depender de un proveedor de pago.
#
# Uso:
#   ./scripts/rerank_local.sh
#
# Al terminar imprime las dos variables que hay que copiar en
# Vercel → Settings → Environment Variables. Deja esta terminal abierta:
# mientras el túnel esté caído, el portal funciona pero sin reordenar.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

PUERTO="${RERANK_PUERTO:-8090}"
export PYTHONPATH=".pylibs:."
export HF_HOME="${HF_HOME:-/home/upta/DeepSeekHarness/upta/.rag-cache/hf}"

CF="$(command -v cloudflared || echo "../tools/cloudflared")"
[ -x "$CF" ] || { echo "ERROR: no encuentro cloudflared (búscalo en ../tools/)"; exit 1; }

# Una clave evita que el túnel quede abierto a cualquiera que dé con la URL.
if [ -z "${RERANK_API_KEY:-}" ]; then
  RERANK_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  echo "[rerank] clave generada para esta sesión"
fi
export RERANK_API_KEY

LOG_RERANK="$(mktemp -t rerank.XXXXXX.log)"
LOG_TUNEL="$(mktemp -t tunel-rerank.XXXXXX.log)"

limpiar() {
  echo
  echo "[rerank] cerrando…"
  [ -n "${PID_RERANK:-}" ] && kill "${PID_RERANK}" 2>/dev/null || true
  [ -n "${PID_TUNEL:-}" ] && kill "${PID_TUNEL}" 2>/dev/null || true
}
trap limpiar EXIT INT TERM

echo "[1/3] Cargando el modelo y sirviendo en :${PUERTO}…"
PYENV_VERSION="${PYENV_VERSION:-3.12.11}" \
  python -m scripts.servir_rerank --puerto "${PUERTO}" --precargar > "${LOG_RERANK}" 2>&1 &
PID_RERANK=$!

for i in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:${PUERTO}/health" >/dev/null 2>&1; then
    echo "      listo tras $((i))s"
    break
  fi
  sleep 1
  if ! kill -0 "${PID_RERANK}" 2>/dev/null; then
    echo "ERROR: el servidor de rerank se cayó. Salida:"; cat "${LOG_RERANK}"; exit 1
  fi
done
curl -sf "http://127.0.0.1:${PUERTO}/health" >/dev/null || { echo "ERROR: no respondió a tiempo"; cat "${LOG_RERANK}"; exit 1; }

echo "[2/3] Abriendo el túnel…"
"${CF}" tunnel --url "http://127.0.0.1:${PUERTO}" --no-autoupdate > "${LOG_TUNEL}" 2>&1 &
PID_TUNEL=$!

URL=""
for i in $(seq 1 60); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "${LOG_TUNEL}" | head -1 || true)"
  [ -n "${URL}" ] && break
  sleep 1
done
[ -n "${URL}" ] || { echo "ERROR: el túnel no dio URL. Salida:"; cat "${LOG_TUNEL}"; exit 1; }

echo "[3/3] Comprobando el endpoint público…"
# Cloudflare tarda unos segundos en propagar el DNS del túnel recién creado:
# se reintenta antes de dar un aviso, para no alarmar en falso.
PUBLICO=""
for i in $(seq 1 12); do
  if curl -sf --max-time 20 -X POST "${URL}/rerank" \
       -H "Content-Type: application/json" \
       -H "Authorization: Bearer ${RERANK_API_KEY}" \
       -d '{"query":"prueba","documents":["documento de prueba"],"top_n":1}' >/dev/null 2>&1; then
    PUBLICO="si"; echo "      responde por la URL pública (tras $((i * 5))s)"; break
  fi
  sleep 5
done
if [ -z "${PUBLICO}" ]; then
  echo "      AVISO: todavía no responde por la URL pública."
  echo "      No es grave: el portal funciona sin rerank hasta que propague."
  echo "      Comprueba en un minuto con:  curl -X POST ${URL}/rerank ..."
fi

cat <<FIN

================================================================
 Copia esto en Vercel → Settings → Environment Variables
================================================================

RERANK_API_URL=${URL}/rerank
RERANK_API_KEY=${RERANK_API_KEY}

Después: Deployments → Redeploy (las variables solo se aplican a un
despliegue nuevo).

Y comprueba el resultado con:

  python3 -m scripts.verificar_despliegue https://<tu-app>.vercel.app

================================================================
 Deja esta terminal abierta. Ctrl-C para cerrar el túnel.
 El modelo está en ${PUERTO} · el túnel en la URL de arriba.
================================================================
FIN

wait "${PID_TUNEL}"
