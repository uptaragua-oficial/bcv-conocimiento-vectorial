"""Compara modelos de **rerank** sobre el corpus del BCV.

`comparar_recuperacion.py` mide la primera etapa (léxica, densa, híbrida). Este
script mide la segunda: dado un mismo conjunto de candidatos, qué cross-encoder
los ordena mejor.

Se evalúa con las mismas dos varas que el resto del proyecto:

  * un conjunto *silver* determinista (consultas derivadas del corpus), y
  * consultas **reales** de usuario, comprobando en qué puesto queda un artículo
    conocido.

Uso:
  python -m scripts.comparar_rerankers
  python -m scripts.comparar_rerankers --consultas 60 --candidatos 30
  python -m scripts.comparar_rerankers --modelo BAAI/bge-reranker-v2-m3

Variables:
  EMBED_DEVICE    cpu | cuda   (por defecto, automático)
  RERANK_DEVICE   cpu | cuda   (por defecto, el de EMBED_DEVICE)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.comparar_recuperacion import (  # noqa: E402
    cargar_corpus,
    construir_evaluacion,
    embed_local,
    indice_bm25,
    metricas,
    puntajes_bm25,
)

#: Modelos comparados por defecto: el que usa el backend local y el que sirve
#: DeepInfra como opción por defecto.
MODELOS = ["BAAI/bge-reranker-v2-m3", "Qwen/Qwen3-Reranker-0.6B"]

#: Consultas reales sobre las que se comprueba el puesto del artículo conocido.
REALES = [
    "¿Qué requisitos exige el BCV para ser operador cambiario autorizado?",
    "¿Cuáles son los requisitos para ser operador cambiario autorizado?",
    "¿Quiénes pueden ser operadores cambiarios?",
    "requisitos para operar como operador cambiario",
    "que se necesita para ser banco operador cambiario autorizado",
    "quien puede actuar como operador cambiario en Venezuela",
    "autorizacion para actuar como operador cambiario",
]
PATRON_OBJETIVO = "Quedan autorizados para actuar"
K = 5
MAX_CARACTERES = 2000


def normalizar(s):
    import numpy as np

    s = np.asarray(s, dtype=np.float64)
    m = float(s.max()) if s.size else 0.0
    return s / m if m > 0 else s


def lineal(lex, den, alpha):
    return alpha * normalizar(den) + (1 - alpha) * normalizar(lex)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compara cross-encoders de rerank")
    ap.add_argument(
        "--consultas",
        type=int,
        default=40,
        help="consultas del conjunto silver (0 = omitir esa parte)",
    )
    ap.add_argument("--candidatos", type=int, default=20, help="candidatos que ve el reranker")
    ap.add_argument("--alpha", type=float, default=0.7, help="fusión híbrida para los candidatos")
    ap.add_argument("--modelo", action="append", default=[], help="modelo a evaluar (repetible)")
    ap.add_argument("--lote", type=int, default=16)
    ap.add_argument(
        "--dispositivo",
        default=None,
        help="cpu | cuda (por defecto, automático: GPU si torch la ve)",
    )
    args = ap.parse_args()

    modelos = args.modelo or MODELOS

    docs = cargar_corpus()
    ix = indice_bm25(docs)
    meta = json.loads((RAIZ / "web/api/_data" / "embeddings_meta.json").read_text(encoding="utf-8"))

    import numpy as np

    matriz = np.fromfile(RAIZ / "web/api/_data" / "vectors.f32", dtype="<f4").reshape(
        meta["n"], meta["dim"]
    )

    evaluacion = construir_evaluacion(docs, args.consultas) if args.consultas > 0 else []
    consultas = [e["query"] for e in evaluacion] + REALES
    print(f"Embebiendo {len(consultas)} consultas con {meta['modelo']}…", flush=True)
    vectores = np.array(embed_local(meta, consultas), dtype=np.float32)
    p_eval = np.maximum(matriz @ vectores[: len(evaluacion)].T, 0)
    p_real = np.maximum(matriz @ vectores[len(evaluacion) :].T, 0)

    objetivo = [
        i for i, d in enumerate(docs) if PATRON_OBJETIVO.lower() in (d[6] or "").lower()
    ]
    print(f"Artículo objetivo: {len(objetivo)} fragmento(s) con {PATRON_OBJETIVO!r}")

    lex_eval = [puntajes_bm25(ix, e["query"]) for e in evaluacion]
    lex_real = [puntajes_bm25(ix, q) for q in REALES]

    def candidatos(lex, den):
        return list(np.argsort(-lineal(lex, den, args.alpha))[: args.candidatos])

    # --- Línea base: sin rerank ---
    if evaluacion:
        acum = {}
        for j, e in enumerate(evaluacion):
            orden = list(np.argsort(-lineal(lex_eval[j], p_eval[:, j], args.alpha)))
            for clave, valor in metricas(docs, orden, e["doc_id"], K).items():
                acum[clave] = acum.get(clave, 0.0) + valor
        n = len(evaluacion)
        print(f"\n=== Conjunto silver · {n} consultas · {args.candidatos} candidatos ===")
        print(f"{'Modelo':<34}{'recall@5':>10}{'MRR':>9}{'nDCG@5':>9}{'ms/consulta':>13}")
        print(
            f"{'— sin rerank —':<34}{acum['recall'] / n:>10.4f}{acum['mrr'] / n:>9.4f}"
            f"{acum['ndcg'] / n:>9.4f}{'—':>13}"
        )
    else:
        print("\n(se omite el conjunto silver: --consultas 0)")

    import os

    from sentence_transformers import CrossEncoder

    dispositivo = args.dispositivo or os.getenv("RERANK_DEVICE") or ""
    if not dispositivo:
        import torch

        dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Dispositivo: {dispositivo}\n")

    resumen = {}
    for nombre in modelos:
        t0 = time.time()
        # 512 tokens bastan: el texto ya viene recortado a MAX_CARACTERES
        # (~500 tokens). Subirlo a 1024 duplica el computo sin cambiar ningun
        # resultado, porque los fragmentos del corpus no llegan a ese limite.
        modelo = CrossEncoder(nombre, device=dispositivo, max_length=512)
        carga = time.time() - t0

        def reordenar(consulta, cand):
            pares = [(consulta, (docs[i][6] or "")[:MAX_CARACTERES]) for i in cand]
            sc = modelo.predict(pares, batch_size=args.lote, show_progress_bar=False)
            return [cand[i] for i in np.argsort(-np.asarray(sc))]

        acum = {}
        ms = float("nan")
        if evaluacion:
            t0 = time.time()
            for j, e in enumerate(evaluacion):
                orden = reordenar(e["query"], candidatos(lex_eval[j], p_eval[:, j]))
                for clave, valor in metricas(docs, orden, e["doc_id"], K).items():
                    acum[clave] = acum.get(clave, 0.0) + valor
            ms = (time.time() - t0) / n * 1000
            print(
                f"{nombre:<34}{acum['recall'] / n:>10.4f}{acum['mrr'] / n:>9.4f}"
                f"{acum['ndcg'] / n:>9.4f}{ms:>13.0f}"
            )

        puestos = []
        for j, q in enumerate(REALES):
            orden = reordenar(q, candidatos(lex_real[j], p_real[:, j]))
            mejor = min((orden.index(i) + 1 for i in objetivo if i in orden), default=None)
            puestos.append(mejor)
        resumen[nombre] = ((acum["ndcg"] / n) if evaluacion else float("nan"), puestos, carga)

    print(f"\n=== Puesto del artículo en {len(REALES)} consultas reales ===")
    print(f"{'Consulta':<58}" + "".join(f"{m.split('/')[-1][:20]:>22}" for m in modelos))
    for j, q in enumerate(REALES):
        fila = f"{q[:56]:<58}"
        for m in modelos:
            p = resumen[m][1][j]
            fila += f"{(p if p else '>'+str(args.candidatos)):>22}"
        print(fila)

    print("\n=== Resumen ===")
    for m in modelos:
        ndcg, puestos, carga = resumen[m]
        aciertos = sum(1 for p in puestos if p and p <= 5)
        silver = f"nDCG@5 {ndcg:.4f}" if ndcg == ndcg else "silver omitido"
        print(f"  {m:<34} top-5 en {aciertos}/{len(REALES)} · {silver} · carga {carga:.1f} s")
    print(f"\n  (artículo objetivo: fragmento(s) {objetivo})")


if __name__ == "__main__":
    main()
