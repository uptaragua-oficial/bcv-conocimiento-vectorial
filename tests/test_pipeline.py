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


def test_ner_combina_motores_por_etiqueta():
    """Las etiquetas de vocabulario cerrado salen de las reglas, sin GLiNER.

    Se midió que GLiNER detecta el 0 % de los tipos de norma, así que en esas
    etiquetas su aportación sería solo ruido. Se comprueba con un tagger falso
    que devuelve una entidad inventada en una etiqueta cerrada: no debe entrar.
    """

    class TaggerFalso:
        def predict_entities(self, texto, etiquetas, threshold=None):
            return [
                {"label": "tipo_de_norma", "text": "inventada"},
                {"label": "institucion", "text": "Banco Central de Venezuela"},
            ]

    ents = ner.extract_entities("Resolución del Banco Central de Venezuela", tagger=TaggerFalso())
    assert not any(e == "tipo_de_norma:inventada" for e in ents), "GLiNER no manda aquí"
    assert "tipo_de_norma:resolución" in ents, "la regla sí"
    # En `institucion`, en cambio, GLiNER es el que aporta
    assert any(e.startswith("institucion:") and "banco central" in e for e in ents)


def test_ner_normaliza_espacios_y_descarta_falsos_positivos():
    """Un salto de línea dentro de una entidad la convertía en otra distinta.

    `banco central de\nvenezuela` y `banco central de venezuela` eran valores
    diferentes, así que filtrar por el correcto perdía fragmentos sin avisar.
    """
    assert ner.normalizar_entidades(["institucion:banco central de\nvenezuela"]) == [
        "institucion:banco central de venezuela"
    ]
    assert ner.normalizar_entidades(["moneda:moneda   nacional"]) == ["moneda:moneda nacional"]
    assert ner.normalizar_entidades(["periodo: 2019 "]) == ["periodo:2019"]
    # Falsos positivos medidos con scripts/comparar_ner.py
    assert ner.normalizar_entidades(["moneda:tipo de cambio"]) == []
    assert ner.normalizar_entidades(["sistema_de_pago:sistema de mercado cambiario"]) == []
    # Deduplica conservando el orden
    assert ner.normalizar_entidades(["moneda:bs", "moneda:bs", "periodo:2019"]) == [
        "moneda:bs",
        "periodo:2019",
    ]


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
