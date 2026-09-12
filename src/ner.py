"""F5 — Reconocimiento de entidades (NER) con GLiNER.

Objetivo (según la propuesta): etiquetar entidades de dominio en la ingesta para
enriquecer los metadatos de cada chunk y habilitar filtros en la búsqueda.

- Modelo principal: **GLiNER** (zero-shot, sin fine-tuning).
- Respaldo: extractor por reglas para el dominio jurídico-económico del BCV,
  de modo que el pipeline siga siendo ejecutable sin el modelo.

Salida: ``data/processed/chunks_ner.jsonl`` (chunks + campo ``entidades``).
"""
from __future__ import annotations

import json
import re

from config import settings

# Etiquetas de entidad del dominio (se pasan a GLiNER como prompt zero-shot).
LABELS = settings.LEGAL_ENTITY_LABELS

# --- Respaldo por reglas (dominio BCV) ---
REGLAS = {
    "moneda": r"\b(bolívar(?:es)?|Bs\.?|USD|dólar(?:es)?|eur(?:os)?|yuan(?:es)?|"
              r"rublo(?:s)?|lira(?:s)?|yen(?:es)?)\b",
    "sistema_de_pago": r"\b(SLBTR|SICET|CCE|Cámara de Compensación Electrónica|"
                       r"sistema de pagos|transferencias?|cheques?)\b",
    "tipo_de_norma": r"\b(ley|resolución|circular|convenio cambiario|providencia|"
                     r"aviso oficial|decreto|reglamento|acto administrativo)\b",
    "institucion": r"\b(BCV|Banco Central de Venezuela|SUDEBAN|SENIAT|Ministerio|"
                   r"Gaceta Oficial|Directorio)\b",
    "indicador_economico": r"\b(INPC|inflación|liquidez monetaria|base monetaria|"
                           r"encaje legal|tipo de cambio|tasa de interés|PIB|reservas internacionales)\b",
    "instrumento_financiero": r"\b(título(?:s)? de cobertura|bono(?:s)?|pagaré(?:s)?|"
                              r"letra(?:s)? del tesoro|acción(?:es)?)\b",
    "materia_cambiaria": r"\b(mesa de cambio|operador cambiario|casa de cambio|"
                         r"régimen cambiario|mercado cambiario)\b",
    "periodo": r"\b(\d{4}|enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
               r"septiembre|octubre|noviembre|diciembre)\b",
}


def _regex_entities(texto: str) -> list[str]:
    encontrados: list[str] = []
    for etiqueta, patron in REGLAS.items():
        for m in re.finditer(patron, texto, flags=re.IGNORECASE):
            encontrados.append(f"{etiqueta}:{m.group(0).strip().lower()}")
    # únicos preservando orden
    return list(dict.fromkeys(encontrados))


def load_tagger():
    """Carga GLiNER si es posible; devuelve ``None`` para usar el respaldo."""
    if not settings.NER_ENABLED:
        return None
    try:
        from gliner import GLiNER

        print(f"Cargando GLiNER: {settings.NER_MODEL} ...")
        return GLiNER.from_pretrained(settings.NER_MODEL)
    except Exception as exc:  # noqa: BLE001
        print(f"[aviso] GLiNER no disponible ({exc}). Se usa el extractor por reglas.")
        return None


def _gliner_entities(tagger, texto: str) -> list[str]:
    ents = tagger.predict_entities(texto[:4000], LABELS, threshold=settings.NER_THRESHOLD)
    return list(dict.fromkeys(f"{e['label']}:{e['text'].strip().lower()}" for e in ents))


def extract_entities(texto: str, tagger=None) -> list[str]:
    """Entidades de un chunk (GLiNER si hay tagger; si no, reglas)."""
    if tagger is not None:
        try:
            return _gliner_entities(tagger, texto)
        except Exception:  # noqa: BLE001
            pass
    return _regex_entities(texto)


def run() -> list[dict]:
    src = settings.PROCESSED_DIR / "chunks.jsonl"
    if not src.exists():
        raise SystemExit("No hay chunks.jsonl. Ejecuta primero: python -m src.chunking")

    chunks = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    tagger = load_tagger()
    motor = "GLiNER" if tagger else "regex"

    for i, c in enumerate(chunks, 1):
        c["entidades"] = extract_entities(c.get("texto", ""), tagger)
        if i % 25 == 0 or i == len(chunks):
            print(f"  NER {i}/{len(chunks)}")

    out = settings.PROCESSED_DIR / "chunks_ner.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    con_ents = sum(1 for c in chunks if c["entidades"])
    print(f"\nResumen NER ({motor}): {con_ents}/{len(chunks)} chunks con entidades")
    print(f"Salida: {out}")
    return chunks


if __name__ == "__main__":
    run()
