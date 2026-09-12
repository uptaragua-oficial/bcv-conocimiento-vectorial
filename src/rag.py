"""RAG conversacional sobre el corpus jurídico del BCV.

Compone la respuesta del asistente a partir de los fragmentos normativos
recuperados por :mod:`src.search`, con **citación obligatoria** de las fuentes.

Dos modos de generación:
  * ``groq``       → LLM vía la API de Groq (OpenAI-compatible), si hay
                     ``GROQ_API_KEY``. Respuesta redactada y conversacional.
  * ``extractivo`` → sin LLM: se ensambla la respuesta citando literalmente los
                     fragmentos más relevantes. Funciona sin credenciales.

Salvaguardas (alineadas con la propuesta):
  1. El asistente **informa**, no asesora legal ni financieramente.
  2. Toda respuesta se sustenta en el contexto recuperado y cita la fuente.
  3. Si el contexto no contiene la respuesta, se declara explícitamente.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from config import settings
from src import search

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

DISCLAIMER = (
    "Este asistente entrega información normativa de fuentes públicas del BCV "
    "y no presta asesoría legal ni financiera. Verifique siempre el texto oficial."
)

SYSTEM_PROMPT = """Eres un asistente especializado en la normativa del Banco Central \
de Venezuela (BCV). Respondes a consultas sobre leyes, resoluciones, convenios \
cambiarios, circulares y actos administrativos.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con la información contenida en el CONTEXTO entregado.
2. Si el contexto no contiene la respuesta, dilo con claridad y sugiere reformular.
3. Cita las fuentes con corchetes al final de cada afirmación, usando el número
   del fragmento: [1], [2], etc.
4. No inventes números de artículos, fechas ni disposiciones.
5. No prestas asesoría legal ni financiera; solo informas sobre el texto normativo.
6. Responde en español, de forma clara, breve y ordenada."""


# ----------------------------------------------------------------------
# Contexto y citas
# ----------------------------------------------------------------------
def construir_contexto(resultados: list[dict]) -> str:
    """Formatea los fragmentos recuperados como contexto numerado."""
    bloques = []
    for i, r in enumerate(resultados, 1):
        cab = f"[{i}] {r.get('tipo_norma', 'Norma')}"
        if r.get("seccion"):
            cab += f" — {r['seccion']}"
        if r.get("materia"):
            cab += f" (materia: {r['materia']})"
        bloques.append(f"{cab}\n{r.get('texto', '').strip()}")
    return "\n\n---\n\n".join(bloques)


def construir_citas(resultados: list[dict]) -> list[dict]:
    citas = []
    for i, r in enumerate(resultados, 1):
        citas.append({
            "n": i,
            "titulo": r.get("titulo"),
            "seccion": r.get("seccion"),
            "tipo_norma": r.get("tipo_norma"),
            "materia": r.get("materia"),
            "fuente_url": r.get("fuente_url"),
            "fragmento": (r.get("texto") or "")[:600],
            "score": r.get("score"),
            "entidades": r.get("entidades") or [],
        })
    return citas


# ----------------------------------------------------------------------
# Generación
# ----------------------------------------------------------------------
def groq_disponible() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


def _historial_mensajes(historial: list[dict] | None) -> list[dict]:
    msgs = []
    for h in (historial or [])[-6:]:  # ventana corta
        rol = "assistant" if h.get("rol") in ("assistant", "bot") else "user"
        contenido = (h.get("contenido") or "").strip()
        if contenido:
            msgs.append({"role": rol, "content": contenido})
    return msgs


def _generar_groq(mensaje: str, contexto: str, historial: list[dict] | None) -> str:
    import requests

    payload = {
        "model": GROQ_MODEL,
        "temperature": 0.1,
        "max_tokens": 900,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            *_historial_mensajes(historial),
            {"role": "user", "content": f"CONTEXTO:\n{contexto}\n\nPREGUNTA: {mensaje}"},
        ],
    }
    resp = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {os.environ['GROQ_API_KEY']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _respuesta_extractiva(mensaje: str, resultados: list[dict]) -> str:
    """Sin LLM: presenta los fragmentos más relevantes como respuesta citada."""
    if not resultados:
        return (
            "No encontré normativa en el corpus que responda a esa consulta. "
            "Intenta reformularla o quitar los filtros aplicados."
        )
    partes = [
        "Estos son los fragmentos normativos más relevantes que encontré en el "
        "corpus jurídico del BCV para tu consulta:\n"
    ]
    for i, r in enumerate(resultados[:3], 1):
        etiqueta = f"{r.get('tipo_norma', 'Norma')}"
        if r.get("seccion"):
            etiqueta += f" — {r['seccion']}"
        texto = (r.get("texto") or "").strip().replace("\n", " ")
        partes.append(f"**[{i}] {etiqueta}:** «{texto[:420]}…»")
    partes.append(
        "\n\n_Modo extractivo (sin modelo de lenguaje): se muestran los fragmentos "
        "recuperados con su fuente. Configure `GROQ_API_KEY` para obtener respuestas "
        "redactadas._"
    )
    return "\n\n".join(partes)


# ----------------------------------------------------------------------
# API pública del módulo
# ----------------------------------------------------------------------
def chat(
    mensaje: str,
    modo: str = "hybrid",
    filtros: dict | None = None,
    limit: int = 5,
    historial: list[dict] | None = None,
    rerank: bool = False,
) -> dict:
    t0 = time.perf_counter()
    resultados = search.search(
        mensaje, modo=modo, limit=limit, filtros=filtros, rerank=rerank, log=True
    )
    contexto = construir_contexto(resultados)

    modo_gen = "extractivo"
    if groq_disponible():
        try:
            respuesta = _generar_groq(mensaje, contexto, historial)
            modo_gen = "groq"
        except Exception as exc:  # noqa: BLE001
            respuesta = (
                f"[No se pudo contactar el modelo de lenguaje: {exc}]\n\n"
                + _respuesta_extractiva(mensaje, resultados)
            )
    else:
        respuesta = _respuesta_extractiva(mensaje, resultados)

    ms = (time.perf_counter() - t0) * 1000
    _log_chat(mensaje, modo, filtros, modo_gen, len(resultados), ms)

    return {
        "respuesta": respuesta,
        "citas": construir_citas(resultados),
        "modo_generacion": modo_gen,
        "modelo": GROQ_MODEL if modo_gen == "groq" else None,
        "n_fragmentos": len(resultados),
        "latencia_ms": round(ms, 1),
        "disclaimer": DISCLAIMER,
    }


def _log_chat(mensaje, modo, filtros, modo_gen, n, ms) -> None:
    ruta = settings.INDEX_DIR / "chat.jsonl"
    registro = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mensaje": mensaje, "modo": modo, "filtros": filtros,
        "modo_generacion": modo_gen, "n_fragmentos": n, "latencia_ms": round(ms, 1),
    }
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "¿Qué requisitos se exigen a los operadores cambiarios?"
    r = chat(q)
    print(f"modo: {r['modo_generacion']} · {r['latencia_ms']} ms · {r['n_fragmentos']} fragmentos\n")
    print(r["respuesta"][:900])
    print("\nCitas:")
    for c in r["citas"][:3]:
        print(f"  [{c['n']}] {c['tipo_norma']} — {c['seccion']}")
