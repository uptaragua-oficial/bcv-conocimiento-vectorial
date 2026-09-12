"""Pruebas unitarias del pipeline (sin necesidad de Weaviate ni de modelos)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".pylibs"))

from src import chunking, evaluate, ner  # noqa: E402

TEXTO_LEY = """
TÍTULO I
DISPOSICIONES FUNDAMENTALES

Artículo 1°. El presente Decreto-Ley tiene por objeto regular el régimen
cambiario de la República Bolivariana de Venezuela y establecer las bases para
el funcionamiento del mercado cambiario nacional.

Artículo 2°. Las operaciones de cambio de moneda extranjera se realizarán a
través de los operadores cambiarios autorizados por el Banco Central de
Venezuela, conforme a las normas que a tal efecto se dicten.

CAPÍTULO II
DE LOS OPERADORES

Artículo 3°. Se entiende por operador cambiario toda persona natural o jurídica
autorizada para realizar operaciones de compra y venta de divisas.
""" + "Texto de relleno. " * 40


def test_chunking_estructura_por_articulo():
    chunks = chunking.chunk_document({
        "doc_id": "doc_test", "titulo": "decreto_ley.pdf", "fuente_url": "http://x",
        "tipo_norma": "Decreto", "materia": "Cambiario", "formato": "pdf",
        "texto": TEXTO_LEY,
    })
    assert chunks, "debe producir chunks"
    assert all(c["estrategia"] == "estructural" for c in chunks)
    secciones = " ".join(c["seccion"] for c in chunks)
    assert "Artículo 1" in secciones
    assert "Artículo 3" in secciones


def test_chunking_respeta_tamano_maximo():
    from config import settings

    chunks = chunking.chunk_document({
        "doc_id": "d", "titulo": "t", "fuente_url": "u",
        "tipo_norma": "Ley", "materia": "General", "formato": "pdf",
        "texto": "palabra " * 5000,
    })
    assert chunks
    assert max(len(c["texto"]) for c in chunks) <= settings.CHUNK_MAX_CHARS


def test_ner_respaldo_por_reglas():
    ents = ner.extract_entities(
        "El Banco Central de Venezuela fija el tipo de cambio en bolívares y "
        "regula el sistema de pagos SLBTR mediante resolución.",
        tagger=None,
    )
    assert any("moneda" in e for e in ents)
    assert any("institucion" in e for e in ents)


def test_metricas_recuperacion():
    rel = {"a"}
    rec = ["x", "a", "b"]
    assert evaluate.recall_at_k(rel, rec, 3) == 1.0
    assert evaluate.recall_at_k(rel, rec, 1) == 0.0
    assert evaluate.reciprocal_rank(rel, rec) == 0.5
    assert 0.0 < evaluate.ndcg_at_k(rel, rec, 3) <= 1.0
    assert evaluate.precision_at_k(rel, rec, 3) == 1 / 3


def test_metricas_no_inflan_con_duplicados():
    """Un documento repetido en el top-k no debe inflar las métricas."""
    rel = {"a"}
    rec = ["a", "a", "a"]  # tres chunks del mismo documento relevante
    assert evaluate.ndcg_at_k(rel, rec, 3) == 1.0          # nDCG <= 1
    assert evaluate.precision_at_k(rel, rec, 3) == 1 / 3   # un único acierto
    assert evaluate.dedupe(rec) == ["a"]


def test_filtros_se_construyen():
    from src.search import build_filter

    assert build_filter(None) is None
    f = build_filter({"materia": "Cambiario", "tipo_norma": "Resolución"})
    assert f is not None
