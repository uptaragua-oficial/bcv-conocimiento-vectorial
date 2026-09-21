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


#: Pares (etiqueta, valor) que el modelo produce con seguridad pero que son
#: incorrectos en este dominio. Se midieron sobre 500 fragmentos con
#: `scripts/comparar_ner.py`; conviene añadir aquí solo lo que se haya medido,
#: no lo que a uno le parezca.
FALSOS_POSITIVOS = {
    ("sistema_de_pago", "sistema de mercado cambiario"),   # 8 casos
    ("sistema_de_pago", "mecanismo de intervención cambiaria"),  # 6 casos
    ("moneda", "tipo de cambio"),                          # es un indicador, no una moneda
}


def normalizar_entidades(entidades: list[str]) -> list[str]:
    """Deja las entidades en forma canónica.

    **Une los espacios, incluidos los saltos de línea.** Sin esto, un mismo
    concepto aparece como valores distintos: `banco central de\nvenezuela` (169
    fragmentos) frente a `banco central de venezuela` (1 266). Un filtro por el
    nombre correcto perdería los 169 sin que nada lo advirtiera, porque para el
    sistema son entidades diferentes.

    Descarta además los falsos positivos medidos y deduplica conservando el orden.
    """
    salida = []
    for e in entidades:
        et, _, v = e.partition(":")
        v = " ".join(v.split())  # colapsa \n, \t y espacios repetidos
        if not v or (et, v) in FALSOS_POSITIVOS:
            continue
        salida.append(f"{et}:{v}")
    return list(dict.fromkeys(salida))


#: Etiquetas en las que las reglas son claramente superiores.
#:
#: Medido con `scripts/comparar_ner.py` sobre 500 fragmentos del corpus, usando
#: los metadatos de la ingesta como verdad de referencia (si un fragmento viene
#: de una Resolución, debería detectarse «resolución» en su texto):
#:
#:   etiqueta              reglas   GLiNER
#:   tipo_de_norma           87 %      0 %      GLiNER no detecta ninguna
#:   indicador_economico    100 %      1 %      («tipo de cambio» incl.)
#:   periodo                  —        ruido     «plazo», «mes», «semana»
#:   materia_cambiaria        —        0 %      no detecta ninguna
#:
#: Pasar etiquetas en lenguaje natural en vez de con guiones bajos NO cambia
#: nada (se midió: 23 % frente a 24 % de cobertura morfológica), así que no era
#: un problema de cómo se escriben las etiquetas.
SOLO_REGLAS = {"tipo_de_norma", "periodo", "materia_cambiaria", "indicador_economico"}


def extract_entities(texto: str, tagger=None) -> list[str]:
    """Entidades de un chunk.

    Sin GLiNER, solo reglas. Con GLiNER, **combinación por etiqueta**: las reglas
    para el vocabulario cerrado, donde son mejores y más precisas, y la unión de
    ambos para las etiquetas abiertas, donde GLiNER aporta términos que las
    reglas pierden por completo («divisas», «tarjetas de crédito», «deuda pública
    nacional», «bancos universales»).
    """
    reglas = _regex_entities(texto)
    if tagger is None:
        return normalizar_entidades(reglas)

    try:
        gliner = _gliner_entities(tagger, texto)
    except Exception as exc:  # noqa: BLE001
        print(f"[aviso] GLiNER falló en un fragmento ({exc}); se usan solo las reglas")
        return normalizar_entidades(reglas)

    combinado = [e for e in reglas if e.split(":", 1)[0] in SOLO_REGLAS]
    combinado += [e for e in reglas if e.split(":", 1)[0] not in SOLO_REGLAS]
    combinado += [e for e in gliner if e.split(":", 1)[0] not in SOLO_REGLAS]
    return normalizar_entidades(combinado)


def run() -> list[dict]:
    src = settings.PROCESSED_DIR / "chunks.jsonl"
    if not src.exists():
        raise SystemExit("No hay chunks.jsonl. Ejecuta primero: python -m src.chunking")

    chunks = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    tagger = load_tagger()
    motor = "combinado (reglas + GLiNER)" if tagger else "reglas (GLiNER no disponible)"

    for i, c in enumerate(chunks, 1):
        c["entidades"] = extract_entities(c.get("texto", ""), tagger)
        # Se deja constancia del motor en los propios datos: antes, si GLiNER no
        # cargaba, el corpus quedaba con entidades de reglas y nada lo indicaba.
        c["motor_ner"] = "combinado" if tagger else "reglas"
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
