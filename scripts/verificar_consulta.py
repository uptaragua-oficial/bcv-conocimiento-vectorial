"""Comprueba en qué puesto queda un fragmento concreto para varias paráfrasis.

Sirve para verificar que una norma conocida sigue siendo recuperable después de
cambiar el corpus, el modelo de embeddings o la lematización: se mide el puesto
del fragmento en BM25, en densa y en la fusión híbrida.

Uso:
  python -m scripts.verificar_consulta \
      --patron "autorizados para operar" \
      --consulta "¿Quiénes pueden ser operadores cambiarios?" \
      --consulta "requisitos para operar como operador cambiario"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.comparar_recuperacion import (  # noqa: E402
    cargar_corpus,
    embed_local,
    fusionar,
    indice_bm25,
    puntajes_bm25,
)


def coseno(matriz: list[float], dim: int, vector: list[float]) -> list[float]:
    scores = []
    for i in range(len(matriz) // dim):
        base = i * dim
        s = 0.0
        for d in range(dim):
            s += matriz[base + d] * vector[d]
        scores.append(s if s > 0 else 0.0)
    return scores


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patron", required=True, help="texto que identifica el fragmento buscado")
    ap.add_argument("--consulta", action="append", required=True)
    ap.add_argument("--vectores", default=str(RAIZ / "web" / "api" / "_data" / "vectors.f32"))
    ap.add_argument("--meta", default=str(RAIZ / "web" / "api" / "_data" / "embeddings_meta.json"))
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    docs = cargar_corpus()
    patron = args.patron.lower()
    objetivo = [i for i, d in enumerate(docs) if patron in (d[6] or "").lower()]
    if not objetivo:
        raise SystemExit(f"Ningún fragmento contiene {args.patron!r}")
    print(f"Objetivo: {len(objetivo)} fragmento(s) con {args.patron!r} de {len(docs)}")
    for i in objetivo:
        print(f"  #{i} · {docs[i][7][:90]}")
        print(f"      {docs[i][6][:160]}…")

    ix = indice_bm25(docs)
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    dim = int(meta["dim"])
    crudo = Path(args.vectores).read_bytes()
    import array

    matriz = array.array("f")
    matriz.frombytes(crudo[: len(crudo) // (dim * 4) * dim * 4])

    densos = embed_local(meta, args.consulta)

    for consulta, dq in zip(args.consulta, densos):
        lex = puntajes_bm25(ix, consulta)
        den = coseno(matriz, dim, dq)
        fus = fusionar(lex, den, args.alpha)

        def puesto(scores):
            orden = sorted(range(len(scores)), key=lambda i: -scores[i])
            mejor = min(orden.index(i) for i in objetivo)
            return mejor + 1

        print(f"\nConsulta: {consulta!r}")
        print(
            f"  puesto → BM25: {puesto(lex)}/{len(docs)} · "
            f"densa: {puesto(den)}/{len(docs)} · "
            f"híbrida (α={args.alpha}): {puesto(fus)}/{len(docs)}"
        )
        orden = sorted(range(len(fus)), key=lambda i: -fus[i])[: args.top]
        for r, i in enumerate(orden, 1):
            marca = "★" if i in objetivo else " "
            print(f"   {marca} {r}. [{fus[i]:.3f}] {docs[i][7][:70]} · {docs[i][6][:80]}")


if __name__ == "__main__":
    main()
