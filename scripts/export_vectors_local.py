"""Genera los vectores del corpus **reutilizando** los ya calculados en local.

Evita por completo tener que vectorizar por API (y por tanto los bloqueos
geográficos de algunos proveedores y cualquier costo): aprovecha los vectores
BGE-M3 que ya produjo el pipeline local y los alinea con el orden exacto de
``web/api/_data/corpus.json``.

Entradas:
  * ``space/data/objects.jsonl`` — propiedades de cada fragmento (incluye `texto`)
  * ``space/data/vectors.npy``   — matriz (N × 1024) con los vectores BGE-M3
  * ``web/api/_data/corpus.json``— corpus que consume Vercel

Salidas:
  * ``web/api/_data/vectors.f32``          — vectores alineados, Float32, L2
  * ``web/api/_data/embeddings_meta.json`` — modelo, dimensiones y conteo

Uso:
  python -m scripts.export_vectors_local
"""
from __future__ import annotations

import json
import struct
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OBJETOS = RAIZ / "space" / "data" / "objects.jsonl"
VECTORES_ORIGEN = RAIZ / "space" / "data" / "vectors.npy"
CORPUS = RAIZ / "web" / "api" / "_data" / "corpus.json"
DESTINO = RAIZ / "web" / "api" / "_data" / "vectors.f32"
META = RAIZ / "web" / "api" / "_data" / "embeddings_meta.json"

MODELO = "BAAI/bge-m3"


def run() -> dict:
    import numpy as np

    for ruta in (OBJETOS, VECTORES_ORIGEN, CORPUS):
        if not ruta.exists():
            raise SystemExit(
                f"Falta {ruta}.\n"
                "  · Si faltan los vectores: ejecuta antes el pipeline y "
                "`python -m scripts.export_index`\n"
                "  · Si falta el corpus: `python -m scripts.export_vercel_index`"
            )

    vectores = np.load(VECTORES_ORIGEN).astype(np.float32)
    objetos = [
        json.loads(l)
        for l in OBJETOS.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    docs = json.loads(CORPUS.read_text(encoding="utf-8"))["docs"]

    if len(vectores) != len(objetos):
        raise SystemExit(
            f"Desajuste: {len(vectores)} vectores para {len(objetos)} objetos"
        )

    # Índice texto → fila de la matriz de vectores
    por_texto: dict[str, int] = {}
    for i, o in enumerate(objetos):
        t = (o.get("texto") or "").strip()
        if t:
            por_texto.setdefault(t, i)

    filas: list[int] = []
    faltantes: list[int] = []
    for i, d in enumerate(docs):
        t = (d[6] or "").strip()
        j = por_texto.get(t)
        if j is None:
            faltantes.append(i)
        else:
            filas.append(j)

    if faltantes:
        raise SystemExit(
            f"{len(faltantes)} fragmentos del corpus no tienen vector asociado "
            f"(posiciones: {faltantes[:5]}…).\n"
            "Regenera el corpus y los vectores con el mismo pipeline."
        )

    dim = int(vectores.shape[1])
    print(f"Alineando {len(filas)} fragmentos con vectores de {dim} dimensiones…")

    with DESTINO.open("wb") as f:
        for j in filas:
            v = vectores[j]
            norma = float((v @ v) ** 0.5) or 1.0
            f.write(struct.pack(f"<{dim}f", *(v / norma).tolist()))

    meta = {
        "n": len(filas),
        "dim": dim,
        "modelo": MODELO,
        "origen": "vectores BGE-M3 calculados en local (sin API)",
        "normalizado": "l2",
        "generado": datetime.now(timezone.utc).isoformat(),
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    mb = DESTINO.stat().st_size / 1e6
    print(f"\nOK · {len(filas)} vectores de {dim} dims → {DESTINO} ({mb:.1f} MB)")
    print(
        "\nSiguiente paso: la consulta SÍ necesita un proveedor de embeddings en\n"
        f"tiempo de ejecución, y debe servir el mismo modelo ({MODELO}). Configura\n"
        "en Vercel:\n"
        "  EMBEDDINGS_API_KEY  = <clave del proveedor>\n"
        "  EMBEDDINGS_BASE_URL = <URL compatible con OpenAI>\n"
        f"  EMBEDDINGS_MODEL    = {MODELO}"
    )
    return meta


if __name__ == "__main__":
    run()
