"""Exporta el corpus jurídico para el modo nativo de Vercel (serverless).

Genera ``web/api/_data/corpus.json``: un arreglo compacto de fragmentos que las
funciones serverless de Vercel usan para la recuperación BM25, sin necesidad de
un backend Python aparte.

Formato (arreglo por documento, para minimizar el tamaño):
  [doc_id, titulo, seccion, tipo_norma, materia, fuente_url, texto, entidades]

Uso:
  python -m scripts.export_vercel_index
"""
from __future__ import annotations

import json
from pathlib import Path

from config import settings

ORIGEN = settings.PROCESSED_DIR / "chunks_ner.jsonl"
DESTINO = Path(__file__).resolve().parent.parent / "web" / "api" / "_data" / "corpus.json"
MIN_CARACTERES = 60


def run() -> dict:
    if not ORIGEN.exists():
        raise SystemExit("Falta data/processed/chunks_ner.jsonl. Ejecuta el pipeline primero.")

    filas = []
    for linea in ORIGEN.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        c = json.loads(linea)
        texto = (c.get("texto") or "").strip()
        if len(texto) < MIN_CARACTERES:
            continue
        filas.append([
            c.get("doc_id") or "",
            c.get("titulo") or "",
            c.get("seccion") or "",
            c.get("tipo_norma") or "Norma",
            c.get("materia") or "General",
            c.get("fuente_url") or "",
            texto,
            c.get("entidades") or [],
        ])

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps({"n": len(filas), "docs": filas}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    mb = DESTINO.stat().st_size / 1e6
    print(f"Exportados {len(filas)} fragmentos -> {DESTINO} ({mb:.2f} MB)")
    return {"n": len(filas), "mb": round(mb, 2)}


if __name__ == "__main__":
    run()
