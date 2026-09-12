"""F9 — Evaluación de la recuperación y logging.

Genera un conjunto de evaluación *silver* a partir del propio corpus jurídico
y calcula métricas estándar de recuperación de información:

  * recall@k
  * precision@k
  * MRR (Mean Reciprocal Rank)
  * nDCG@k

Se comparan las estrategias: ``semantic``, ``keyword``, ``hybrid`` y
``hybrid`` con re-ranking. Los resultados se escriben en
``data/index/evaluation_report.json``.

Nota metodológica: al no existir juicios de relevancia humanos, se construye un
conjunto *silver* por auto-recuperación (la consulta se deriva de un chunk y su
propio documento es relevante). Es un proxy honesto y reproducible para el MVP;
en producción se sustituiría por juicios de relevancia del BCV.
"""
from __future__ import annotations

import json
import math
import random
import re
from datetime import datetime, timezone

from config import settings
from src import search

random.seed(42)


# ----------------------------------------------------------------------
# Conjunto de evaluación (silver)
# ----------------------------------------------------------------------
def _cargar_chunks() -> list[dict]:
    path = settings.PROCESSED_DIR / "chunks_ner.jsonl"
    if not path.exists():
        raise SystemExit("No hay chunks_ner.jsonl. Ejecuta primero: python -m src.ner")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _query_desde_chunk(c: dict) -> str | None:
    """Deriva una consulta natural a partir de la sección/título del chunk."""
    sec = (c.get("seccion") or "").strip()
    titulo = (c.get("titulo") or "").replace("_", " ").replace(".pdf", "")
    titulo = re.sub(r"\b\d+[\d_.-]*\b", " ", titulo).strip()
    palabras = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{4,}", c.get("texto", "")) if w.lower() not in
                {"para", "como", "según", "sobre", "entre", "desde", "hasta", "cuando", "toda", "todos",
                 "mismo", "misma", "serán", "deberá", "podrá", "artículo", "único"}]
    if not palabras:
        return None
    muestra = " ".join(random.sample(palabras, min(6, len(palabras))))
    if sec and titulo:
        return f"{sec} de {titulo}: {muestra}"
    return f"{titulo}: {muestra}"


def build_eval_set(n: int = 40) -> list[dict]:
    """Crea el conjunto *silver*: consulta → doc_id relevante."""
    chunks = [c for c in _cargar_chunks() if len(c.get("texto", "")) > 200]
    if not chunks:
        raise SystemExit("No hay chunks suficientes para evaluar.")
    muestra = random.sample(chunks, min(n, len(chunks)))
    evals: list[dict] = []
    for c in muestra:
        q = _query_desde_chunk(c)
        if not q:
            continue
        evals.append({
            "query": q,
            "doc_id_relevante": c["doc_id"],
            "seccion_origen": c.get("seccion"),
            "chunk_hash": c.get("doc_hash"),
        })
    ruta = settings.INDEX_DIR / "eval_set.jsonl"
    with ruta.open("w", encoding="utf-8") as f:
        for e in evals:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Conjunto de evaluación: {len(evals)} consultas -> {ruta}")
    return evals


# ----------------------------------------------------------------------
# Métricas
# ----------------------------------------------------------------------
def recall_at_k(relevantes: set, recuperados: list, k: int) -> float:
    if not relevantes:
        return 0.0
    return len(relevantes & set(recuperados[:k])) / len(relevantes)


def precision_at_k(relevantes: set, recuperados: list, k: int) -> float:
    if k == 0:
        return 0.0
    return len(relevantes & set(recuperados[:k])) / k


def reciprocal_rank(relevantes: set, recuperados: list) -> float:
    for i, r in enumerate(recuperados, 1):
        if r in relevantes:
            return 1.0 / i
    return 0.0


def ndcg_at_k(relevantes: set, recuperados: list, k: int) -> float:
    dcg = sum(
        1.0 / math.log2(i + 1)
        for i, r in enumerate(recuperados[:k], 1)
        if r in relevantes
    )
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevantes), k) + 1))
    return dcg / idcg if idcg else 0.0


# ----------------------------------------------------------------------
# Evaluación
# ----------------------------------------------------------------------
ESTRATEGIAS = [
    ("semantic", {"modo": "semantic"}),
    ("keyword", {"modo": "keyword"}),
    ("hybrid_a0.5", {"modo": "hybrid", "alpha": 0.5}),
    ("hybrid_a0.7", {"modo": "hybrid", "alpha": 0.7}),
    ("hybrid+rerank", {"modo": "hybrid", "alpha": 0.5, "rerank": True}),
]


def evaluate(eval_set: list[dict], top_k: int = 5, estrategias=None) -> dict:
    estrategias = estrategias or ESTRATEGIAS
    informe: dict = {
        "generado": datetime.now(timezone.utc).isoformat(),
        "n_consultas": len(eval_set),
        "top_k": top_k,
        "estrategias": {},
    }

    for nombre, cfg in estrategias:
        print(f"\nEvaluando estrategia: {nombre}")
        acum = {"recall": 0.0, "precision": 0.0, "mrr": 0.0, "ndcg": 0.0, "latencia_ms": 0.0}
        for e in eval_set:
            res = search.search(
                e["query"], limit=top_k, log=False,
                modo=cfg.get("modo", "hybrid"),
                alpha=cfg.get("alpha", 0.5),
                rerank=cfg.get("rerank", False),
            )
            # Relevante = mismo documento de origen (o el mismo chunk).
            recuperados = [r["doc_id"] for r in res]
            hashes = [r["uuid"] for r in res]
            relevantes = {e["doc_id_relevante"]}
            acum["recall"] += recall_at_k(relevantes, recuperados, top_k)
            acum["precision"] += precision_at_k(relevantes, recuperados, top_k)
            acum["mrr"] += reciprocal_rank(relevantes, recuperados)
            acum["ndcg"] += ndcg_at_k(relevantes, recuperados, top_k)
            acum["latencia_ms"] += float(res[0].get("_ms", 0)) if res else 0.0
            del hashes
        n = len(eval_set) or 1
        informe["estrategias"][nombre] = {
            "recall@k": round(acum["recall"] / n, 4),
            "precision@k": round(acum["precision"] / n, 4),
            "mrr": round(acum["mrr"] / n, 4),
            "ndcg@k": round(acum["ndcg"] / n, 4),
        }
        m = informe["estrategias"][nombre]
        print(f"  recall@{top_k}={m['recall@k']:.3f}  precision@{top_k}={m['precision@k']:.3f}  "
              f"MRR={m['mrr']:.3f}  nDCG@{top_k}={m['ndcg@k']:.3f}")

    # Mejor estrategia por nDCG
    mejor = max(informe["estrategias"].items(), key=lambda kv: kv[1]["ndcg@k"])
    informe["mejor_estrategia"] = {"nombre": mejor[0], **mejor[1]}

    ruta = settings.INDEX_DIR / "evaluation_report.json"
    ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nMejor estrategia: {mejor[0]} (nDCG@{top_k}={mejor[1]['ndcg@k']:.3f})")
    print(f"Informe: {ruta}")
    return informe


def run(n_consultas: int = 40, top_k: int = 5) -> dict:
    evals = build_eval_set(n_consultas)
    return evaluate(evals, top_k=top_k)


if __name__ == "__main__":
    run()
