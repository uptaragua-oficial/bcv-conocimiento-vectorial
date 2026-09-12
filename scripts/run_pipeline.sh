#!/usr/bin/env bash
# ============================================================
# Ejecuta el pipeline completo del MVP (F2 → F9)
# ============================================================
# Uso:
#   ./scripts/run_pipeline.sh            # pipeline completo
#   ./scripts/run_pipeline.sh --from F6  # desde una fase concreta
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH=".pylibs:."
export HF_HOME="${HF_HOME:-/home/upta/DeepSeekHarness/upta/.rag-cache/hf}"

DESDE="${2:-F2}"

paso() {
  local fase="$1"; shift
  local modulo="$1"; shift
  echo
  echo "==================================================================="
  echo "  $fase  ·  python -m $modulo"
  echo "==================================================================="
  python -m "$modulo" "$@"
}

empezar=false
[ "$DESDE" = "F2" ] && empezar=true || true

if [ "$DESDE" = "F2" ]; then paso "F2  Ingesta"            src.ingest; fi
if [ "$DESDE" = "F2" ] || [ "$DESDE" = "F3" ]; then paso "F3  Extracción" src.extract; fi
if [ "$DESDE" = "F2" ] || [ "$DESDE" = "F4" ]; then paso "F4  Chunking"   src.chunking; fi
if [ "$DESDE" = "F2" ] || [ "$DESDE" = "F5" ]; then paso "F5  NER"        src.ner; fi
if [ "$DESDE" = "F2" ] || [ "$DESDE" = "F6" ]; then paso "F6+F7  Indexado" src.index --recreate; fi
if [ "$DESDE" = "F2" ] || [ "$DESDE" = "F9" ]; then paso "F9  Evaluación" src.evaluate; fi

echo
echo "Pipeline finalizado. Resultados en data/processed y data/index."
