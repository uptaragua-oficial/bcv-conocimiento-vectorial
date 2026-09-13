"""Compara la calidad de recuperación entre modelos de embeddings.

Mide, sobre el **mismo** conjunto de consultas y el **mismo** corpus, las
métricas estándar de recuperación de información:

  * recall@k
  * precisión@k
  * MRR   (Mean Reciprocal Rank)
  * nDCG@k

para tres estrategias: BM25 (léxica), densa (coseno) e híbrida (fusión lineal).
Así se puede decidir con datos si merece la pena cambiar de modelo.

El conjunto de evaluación se construye de forma **determinista** a partir del
corpus (semilla fija), de modo que todos los modelos se miden con las mismas
consultas. Es un conjunto *silver* por auto-recuperación: la consulta se deriva
de un fragmento y su propio documento cuenta como relevante.

Uso:
  # Solo BM25 (no necesita vectores ni modelos)
  python -m scripts.comparar_recuperacion

  # Un modelo local (sentence-transformers)
  python -m scripts.comparar_recuperacion \
      --vectores data/processed/vectores_e5.f32 \
      --meta     data/processed/vectores_e5.meta.json \
      --nombre   e5-large

  # Varios a la vez (se imprimen comparados)
  python -m scripts.comparar_recuperacion --conjunto bge:...:... --conjunto e5:...:...

  # Modelo por API (necesita EMBEDDINGS_API_KEY; útil desde Colab para OpenAI)
  python -m scripts.comparar_recuperacion --vectores ... --meta ... --api

Parámetros:  --k 5   --consultas 40   --alpha 0.5
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / "web" / "api" / "_data" / "corpus.json"

# BM25: mismos parámetros que la implementación de Vercel
K1, B = 1.2, 0.75


# ----------------------------------------------------------------------
# Conjunto de evaluación (determinista)
# ----------------------------------------------------------------------
def cargar_corpus() -> list[list]:
    if not CORPUS.exists():
        raise SystemExit(f"No existe {CORPUS}. Ejecuta: python -m scripts.export_vercel_index")
    return json.loads(CORPUS.read_text(encoding="utf-8"))["docs"]


def _normalizar_texto(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip())


def construir_evaluacion(docs: list[list], n: int) -> list[dict]:
    """Consultas derivadas del corpus (semilla fija → reproducible)."""
    random.seed(42)
    candidatos = [d for d in docs if len(d[6]) > 200]
    muestra = random.sample(candidatos, min(n, len(candidatos)))

    prohibidas = {
        "para", "como", "según", "sobre", "entre", "desde", "hasta", "cuando",
        "toda", "todos", "mismo", "misma", "serán", "deberá", "podrá", "artículo",
        "único", "presente", "través", "mediante",
    }
    evaluacion = []
    for d in muestra:
        palabras = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{4,}", d[6]) if w.lower() not in prohibidas]
        if not palabras:
            continue
        titulo = re.sub(r"\b\d+[\d_.-]*\b", " ", (d[1] or "")).replace("_", " ").replace(".pdf", "").strip()
        trozo = " ".join(random.sample(palabras, min(6, len(palabras))))
        consulta = f"{d[2]} de {titulo}: {trozo}" if d[2] and titulo else f"{titulo}: {trozo}"
        evaluacion.append({"query": consulta, "doc_id": d[0]})

    # Sin duplicar consultas
    vistas, salida = set(), []
    for e in evaluacion:
        if e["query"] not in vistas:
            vistas.add(e["query"])
            salida.append(e)
    return salida


# ----------------------------------------------------------------------
# Estrategias
# ----------------------------------------------------------------------
def tokenizar(texto: str) -> list[str]:
    """Igual que la implementación de Vercel: sin acentos y recortado a raíz."""
    import unicodedata

    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [raiz(p) for p in re.findall(r"[a-z0-9]{2,}", t)]


LARGO_RAIZ = 7


def raiz(token: str) -> str:
    """Recorta a 7 caracteres para unir plurales y géneros del español."""
    return token[:LARGO_RAIZ] if len(token) > LARGO_RAIZ else token


def indice_bm25(docs: list[list]) -> dict:
    tf, dl, df = [], [], {}
    for d in docs:
        toks = tokenizar(d[6])
        dl.append(len(toks) or 1)
        f: dict[str, int] = {}
        for w in toks:
            f[w] = f.get(w, 0) + 1
        tf.append(f)
        for w in f:
            df[w] = df.get(w, 0) + 1
    return {"tf": tf, "dl": dl, "df": df, "n": len(docs), "avgdl": sum(dl) / (len(dl) or 1)}


def puntajes_bm25(ix: dict, consulta: str) -> list[float]:
    scores = [0.0] * ix["n"]
    for t in tokenizar(consulta):
        d = ix["df"].get(t, 0)
        if not d:
            continue
        peso = math.log(1 + (ix["n"] - d + 0.5) / (d + 0.5))
        for i in range(ix["n"]):
            f = ix["tf"][i].get(t)
            if not f:
                continue
            norma = 1 - B + B * ix["dl"][i] / ix["avgdl"]
            scores[i] += peso * (f * (K1 + 1)) / (f + K1 * norma)
    return scores


def _normalizar(scores: list[float]) -> list[float]:
    m = max(scores) if scores else 0.0
    return [s / m for s in scores] if m > 0 else scores


def fusionar(lexicos: list[float], densos: list[float], alpha: float) -> list[float]:
    ll, dd = _normalizar(lexicos), _normalizar(densos)
    return [alpha * d + (1 - alpha) * l for l, d in zip(ll, dd)]


# ----------------------------------------------------------------------
# Embeddings de las consultas
# ----------------------------------------------------------------------
def embed_local(meta: dict, consultas: list[str]) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer
    import torch

    dispositivo = os.getenv("EMBED_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
    prefijo = meta.get("prefijo_consulta", "") or ""
    print(f"  Embebiendo {len(consultas)} consultas con {meta['modelo']} en {dispositivo}…")
    modelo = SentenceTransformer(meta["modelo"], device=dispositivo)
    v = modelo.encode([prefijo + c for c in consultas], normalize_embeddings=True, convert_to_numpy=True)
    return [fila.tolist() for fila in v]


def embed_api(meta: dict, consultas: list[str]) -> list[list[float]]:
    import urllib.request

    clave = os.getenv("EMBEDDINGS_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not clave:
        raise SystemExit("--api requiere EMBEDDINGS_API_KEY (o OPENAI_API_KEY)")
    formato = meta.get("formato", "openai")
    url = os.getenv("EMBEDDINGS_URL") or meta.get("url_sugerida", "")
    prefijo = meta.get("prefijo_consulta", "") or ""
    print(f"  Embebiendo {len(consultas)} consultas vía API ({formato})…")

    salida = []
    for c in consultas:
        entrada = prefijo + c
        cuerpo = {"inputs": [entrada]} if formato == "huggingface" else {
            "model": meta["modelo"], "input": [entrada]
        }
        req = urllib.request.Request(
            url, data=json.dumps(cuerpo).encode(), method="POST",
            headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            datos = json.loads(r.read())
        vec = datos[0] if formato == "huggingface" else datos["data"][0]["embedding"]
        salida.append(vec)
    return salida


# ----------------------------------------------------------------------
# Métricas
# ----------------------------------------------------------------------
def _unicos(seq):
    vistos, salida = set(), []
    for x in seq:
        if x not in vistos:
            vistos.add(x)
            salida.append(x)
    return salida


def metricas(docs: list[list], ranking_idx: list[int], relevante: str, k: int) -> dict:
    docs_orden = _unicos([docs[i][0] for i in ranking_idx[:k]])
    aciertos = 1 if relevante in docs_orden else 0
    pos = docs_orden.index(relevante) + 1 if relevante in docs_orden else 0
    dcg = 1 / math.log2(pos + 1) if pos else 0.0
    idcg = 1 / math.log2(2)
    return {
        "recall": float(aciertos),
        "precision": aciertos / k,
        "mrr": (1 / pos) if pos else 0.0,
        "ndcg": (dcg / idcg) if idcg else 0.0,
    }


def evaluar(nombre: str, docs, evaluacion, ix, k, densos_por_consulta=None, alpha=0.5):
    acum = {"lexica": {}, "densa": {}, "hibrida": {}}
    estrategias = ["lexica"] + (["densa", "hibrida"] if densos_por_consulta else [])

    for j, e in enumerate(evaluacion):
        lex = puntajes_bm25(ix, e["query"])
        if not any(lex):
            continue
        rankings = {"lexica": sorted(range(len(lex)), key=lambda i: -lex[i])}
        if densos_por_consulta:
            d = densos_por_consulta[j]
            rankings["densa"] = sorted(range(len(d)), key=lambda i: -d[i])
            rankings["hibrida"] = sorted(range(len(d)), key=lambda i: -fusionar(lex, d, alpha)[i])

        for est in estrategias:
            m = metricas(docs, rankings[est], e["doc_id"], k)
            for clave, valor in m.items():
                acum[est][clave] = acum[est].get(clave, 0.0) + valor

    n = max(len(evaluacion), 1)
    return {
        est: {clave: round(v / n, 4) for clave, v in vals.items()}
        for est, vals in acum.items()
        if vals
    }


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def _leer_conjunto(vectores: str, meta: str, nombre: str) -> dict:
    import numpy as np

    meta_datos = json.loads(Path(meta).read_text(encoding="utf-8"))
    arr = np.fromfile(vectores, dtype="<f4").reshape(meta_datos["n"], meta_datos["dim"])
    return {"nombre": nombre or meta_datos["modelo"], "meta": meta_datos, "matriz": arr}


def main() -> None:
    ap = argparse.ArgumentParser(description="Compara modelos de embeddings en la recuperación")
    ap.add_argument("--vectores", help="archivo .f32 del conjunto a evaluar")
    ap.add_argument("--meta", help="json con la meta de ese conjunto")
    ap.add_argument("--nombre", help="etiqueta del conjunto")
    ap.add_argument("--conjunto", action="append", default=[],
                    help="nombre:ruta.f32:ruta.meta.json (repetible)")
    ap.add_argument("--api", action="store_true", help="embeber las consultas vía API")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--consultas", type=int, default=40)
    ap.add_argument("--alpha", type=float, default=0.5)
    args = ap.parse_args()

    docs = cargar_corpus()
    evaluacion = construir_evaluacion(docs, args.consultas)
    print(f"Corpus: {len(docs)} fragmentos · evaluación: {len(evaluacion)} consultas · k={args.k}\n")

    ix = indice_bm25(docs)

    conjuntos = []
    if args.vectores and args.meta:
        conjuntos.append(_leer_conjunto(args.vectores, args.meta, args.nombre))
    for espec in args.conjunto:
        partes = espec.split(":")
        if len(partes) != 3:
            raise SystemExit(f"--conjunto mal formado: {espec} (usa nombre:vectores.f32:meta.json)")
        conjuntos.append(_leer_conjunto(partes[1], partes[2], partes[0]))

    resultados = {}
    print("Evaluando BM25…")
    resultados["BM25 (léxico)"] = evaluar("bm25", docs, evaluacion, ix, args.k)

    for conjunto in conjuntos:
        print(f"\nEvaluando {conjunto['nombre']}…")
        consultas = [e["query"] for e in evaluacion]
        vectores_q = (
            embed_api(conjunto["meta"], consultas)
            if args.api
            else embed_local(conjunto["meta"], consultas)
        )
        import numpy as np

        densos = [list(conjunto["matriz"] @ np.asarray(v, dtype="<f4")) for v in vectores_q]
        resultados[conjunto["nombre"]] = evaluar(
            conjunto["nombre"], docs, evaluacion, ix, args.k, densos, args.alpha
        )

    # --- Tabla comparativa ---
    print(f"\n{'=' * 78}")
    print(f"{'Estrategia':<34}{'recall@' + str(args.k):>12}{'MRR':>10}{'nDCG@' + str(args.k):>12}")
    print("-" * 78)
    for nombre, ests in resultados.items():
        for est, m in ests.items():
            etiqueta = f"{nombre} · {est}"
            print(
                f"{etiqueta:<34}{m.get('recall', 0):>12.3f}"
                f"{m.get('mrr', 0):>10.3f}{m.get('ndcg', 0):>12.3f}"
            )
    print("=" * 78)

    mejores = [
        (f"{n} · {e}", m.get("ndcg", 0))
        for n, ests in resultados.items() for e, m in ests.items()
    ]
    if mejores:
        top = max(mejores, key=lambda x: x[1])
        print(f"\nMejor por nDCG@{args.k}: {top[0]} ({top[1]:.3f})")


if __name__ == "__main__":
    main()
