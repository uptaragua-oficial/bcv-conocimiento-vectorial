"""Pruebas del asistente RAG y de la API (sin depender de Weaviate).

Se prueban las funciones puras de composición de contexto/citas y el contrato
HTTP de `/chat`, sustituyendo la recuperación por un doble de prueba.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / ".pylibs"))

from src import rag  # noqa: E402

RESULTADOS = [
    {
        "n": 1, "doc_id": "doc_1", "titulo": "convenio.pdf",
        "seccion": "Artículo 12", "tipo_norma": "Convenio cambiario",
        "materia": "Cambiario", "fuente_url": "https://www.bcv.org.ve/x.pdf",
        "texto": "Artículo 12. Quedan autorizados para actuar como operadores cambiarios…",
        "score": 0.91, "entidades": ["institucion:bcv"],
    },
    {
        "n": 2, "doc_id": "doc_2", "titulo": "resolucion.pdf",
        "seccion": "Artículo 6", "tipo_norma": "Resolución",
        "materia": "Cambiario", "fuente_url": "https://www.bcv.org.ve/y.pdf",
        "texto": "Artículo 6. Los interesados podrán presentar cotizaciones…",
        "score": 0.80, "entidades": [],
    },
]


# ---------------- Funciones puras ----------------
def test_construir_contexto_numera_y_etiqueta():
    ctx = rag.construir_contexto(RESULTADOS)
    assert "[1]" in ctx and "[2]" in ctx
    assert "Convenio cambiario" in ctx
    assert "Artículo 12" in ctx
    assert "Cambiario" in ctx


def test_construir_citas_mapea_campos():
    citas = rag.construir_citas(RESULTADOS)
    assert len(citas) == 2
    c = citas[0]
    assert c["n"] == 1
    assert c["fuente_url"].endswith(".pdf")
    assert len(c["fragmento"]) <= 600


def test_historial_normaliza_roles_y_recorta():
    historial = [{"rol": "user", "contenido": f"m{i}"} for i in range(10)]
    historial.append({"rol": "assistant", "contenido": "respuesta"})
    msgs = rag._historial_mensajes(historial)
    assert len(msgs) <= 6
    assert msgs[-1] == {"role": "assistant", "content": "respuesta"}
    assert all(m["role"] in ("user", "assistant") for m in msgs)


def test_respuesta_extractiva_con_y_sin_resultados():
    vacia = rag._respuesta_extractiva("nada", [])
    assert "No encontré" in vacia

    con = rag._respuesta_extractiva("algo", RESULTADOS)
    assert "Artículo 12" in con
    assert "[1]" in con


def test_disclaimer_presente():
    assert "no presta asesoría" in rag.DISCLAIMER


# ---------------- Contrato HTTP ----------------
@pytest.fixture()
def cliente(monkeypatch):
    from fastapi.testclient import TestClient

    from src import api as api_mod

    def falso_chat(mensaje, modo="hybrid", filtros=None, limit=5, historial=None, rerank=False):
        return {
            "respuesta": "Respuesta de prueba con cita [1].",
            "citas": rag.construir_citas(RESULTADOS),
            "modo_generacion": "extractivo",
            "modelo": None,
            "n_fragmentos": len(RESULTADOS),
            "latencia_ms": 12.3,
            "disclaimer": rag.DISCLAIMER,
        }

    monkeypatch.setattr(api_mod.rag, "chat", falso_chat)
    return TestClient(api_mod.app)


def test_chat_devuelve_respuesta_y_citas(cliente):
    r = cliente.post("/chat", json={"mensaje": "¿operadores cambiarios?", "limit": 3})
    assert r.status_code == 200
    d = r.json()
    assert "cita" in d["respuesta"]
    assert len(d["citas"]) == 2
    assert d["disclaimer"]


def test_chat_rechaza_modo_invalido(cliente):
    r = cliente.post("/chat", json={"mensaje": "consulta", "modo": "magico"})
    assert r.status_code == 400


def test_chat_valida_mensaje_minimo(cliente):
    r = cliente.post("/chat", json={"mensaje": ""})
    assert r.status_code == 422


# ---------------- Selección de proveedor de LLM ----------------
def test_proveedor_llm_sin_claves(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert rag.proveedor_llm() is None
    assert rag.llm_disponible() is False


def test_proveedor_llm_prioriza_deepseek(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_prueba")
    assert rag.proveedor_llm()["nombre"] == "groq"

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-prueba")
    p = rag.proveedor_llm()
    assert p["nombre"] == "deepseek"
    assert p["modelo"] == "deepseek-flash"
    assert p["url"].startswith("https://api.deepseek.com")
    assert rag.llm_disponible() is True


def test_proveedor_llm_respeta_modelo_configurado(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-prueba")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    assert rag.proveedor_llm()["modelo"] == "deepseek-v4-pro"


def test_deepseek_desactiva_thinking_por_defecto(monkeypatch):
    """El modo thinking viene activado por defecto en DeepSeek; lo apagamos."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-prueba")
    monkeypatch.delenv("DEEPSEEK_THINKING", raising=False)
    assert rag.proveedor_llm()["thinking"] == "disabled"

    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
    assert rag.proveedor_llm()["thinking"] == "enabled"
