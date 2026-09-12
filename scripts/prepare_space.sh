#!/usr/bin/env bash
# ============================================================
# Ensambla el directorio listo para publicar en HuggingFace Spaces.
# ============================================================
# Uso:
#   ./scripts/prepare_space.sh [destino]
#
# Genera (por defecto en /tmp/bcv-space) la estructura que se sube al Space:
#   Dockerfile  README.md  requirements.txt  entrypoint.sh
#   import_index.py  data/{objects.jsonl,vectors.npy,meta.json}
#
# Requiere haber exportado antes el índice:
#   python -m scripts.export_index
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."
DEST="${1:-/tmp/bcv-space}"

if [ ! -f space/data/objects.jsonl ] || [ ! -f space/data/vectors.npy ]; then
  echo "ERROR: falta el índice precomputado en space/data/."
  echo "Ejecuta primero:  python -m scripts.export_index"
  exit 1
fi

rm -rf "$DEST"
mkdir -p "$DEST/data"

cp space/Dockerfile space/README.md space/requirements.txt \
   space/entrypoint.sh space/import_index.py "$DEST/"
cp space/data/objects.jsonl space/data/vectors.npy space/data/meta.json "$DEST/data/"

echo "Space preparado en: $DEST"
echo
find "$DEST" -type f -printf '  %-30P %8s bytes\n' | sort
echo
echo "Siguientes pasos:"
echo "  cd $DEST"
echo "  git init -b main"
echo "  git remote add space https://huggingface.co/spaces/<usuario>/<space>"
echo "  git add -A && git commit -m 'Backend de consulta normativa del BCV'"
echo "  git push space main"
