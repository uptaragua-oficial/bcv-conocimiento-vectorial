"""Carga el índice precomputado en Weaviate (usado al arrancar el Space).

Lee ``data/objects.jsonl`` y ``data/vectors.npy`` (generados por
``scripts/export_index.py``) y los inserta en la colección `Normativa`
**sin recalcular embeddings**, por lo que el arranque tarda segundos.

Uso:
  python import_index.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

# Permitir ejecutarlo desde /app (Space) o desde la raíz del proyecto (local)
for candidato in (Path("/app"), DATA.parent.parent):
    if (candidato / "src").is_dir():
        sys.path.insert(0, str(candidato))
        break

import numpy as np  # noqa: E402

from config import settings  # noqa: E402
from src import store  # noqa: E402

RE_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


def _sanear(props: dict) -> dict:
    """Garantiza que las fechas cumplan RFC3339 (requisito de Weaviate DATE)."""
    fecha = props.get("fecha_publicacion")
    if fecha is None:
        return props
    s = str(fecha).strip()
    if not RE_RFC3339.match(s):
        props.pop("fecha_publicacion", None)
        return props
    s = s.replace(" ", "T", 1)
    if not s.endswith("Z") and "+" not in s:
        s += "Z"
    props["fecha_publicacion"] = s
    return props



def run() -> dict:
    ruta_objs = DATA / "objects.jsonl"
    ruta_vecs = DATA / "vectors.npy"
    if not ruta_objs.exists() or not ruta_vecs.exists():
        raise SystemExit(f"No se encontró el índice precomputado en {DATA}")

    vectores = np.load(ruta_vecs)
    objetos = [json.loads(l) for l in ruta_objs.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Índice precomputado: {len(objetos)} objetos · dim={vectores.shape[1]}", flush=True)

    with store.collection() as (_client, col):
        actuales = store.count_objects(col)
        if actuales >= len(objetos):
            print(f"La colección ya tiene {actuales} objetos; nada que importar.", flush=True)
            return {"importados": 0, "total": actuales}

        importados = 0
        with col.batch.dynamic() as batch:
            for props, vec in zip(objetos, vectores):
                props.setdefault("fuente_url", "")
                props.setdefault("texto", "")
                props.setdefault("doc_id", "")
                batch.add_object(properties=_sanear(dict(props)), vector=vec.tolist())
                importados += 1
                if importados % 500 == 0:
                    print(f"  importados {importados}/{len(objetos)}", flush=True)
        total = store.count_objects(col)

    print(f"Importación finalizada: {importados} objetos · {total} en la colección", flush=True)
    return {"importados": importados, "total": total}


if __name__ == "__main__":
    run()
