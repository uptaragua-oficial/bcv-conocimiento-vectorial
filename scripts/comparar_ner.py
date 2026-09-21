"""Compara motores de NER sobre el corpus real: reglas, GLiNER y combinaciones.

El problema de evaluar NER sin anotación humana es que «entidad correcta» es un
juicio. Aquí se evita en lo posible con **tres pruebas objetivas**:

1. **Recall contra los metadatos del propio corpus.** Cada fragmento sabe de qué
   tipo de norma viene (`tipo_norma`), dato que se asignó en la ingesta y no tiene
   nada que ver con el NER. Si un fragmento viene de una Resolución, un buen
   detector de `tipo_de_norma` debería encontrar la palabra «resolución» en su
   texto. Además se mide el **techo**: cuántos de esos fragmentos contienen el
   término de verdad. Sin ese techo, un recall del 60 % podría ser perfecto.

2. **Cobertura morfológica.** Una lista de formas que *deberían* detectarse,
   incluyendo plurales y variantes de género («operadores cambiarios», «casas de
   cambio», «resoluciones»). Mide el punto débil conocido de las reglas.

3. **Ruido en vocabulario cerrado.** Para las etiquetas cuya lista de valores
   válidos es finita y conocida (moneda, tipo de norma, sistema de pago…), se
   listan los valores que produce cada motor **fuera** de esa lista. Un valor de
   más es una variante que las reglas pierden o un error de etiquetado; se
   informan los más frecuentes para poder juzgarlos.

Uso:
  python -m scripts.comparar_ner --muestra 500
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from config import settings  # noqa: E402
from src import ner  # noqa: E402

#: Fragmentos por debajo de esto no llegan al corpus (ver export_vercel_index.py).
MIN_CARACTERES = 60

#: GLiNER compara el **nombre de la etiqueta como texto** contra el fragmento.
#: `sistema_de_pago` con guiones bajos no es lenguaje natural, y cabía sospechar
#: que eso degradara la detección. Este mapa permite pasarle las etiquetas
#: escritas como se escribirían en español y volver luego al nombre canónico.
PROMPTS_NATURALES = {
    "moneda": "moneda",
    "instrumento_financiero": "instrumento financiero",
    "sistema_de_pago": "sistema de pago",
    "tipo_de_norma": "tipo de norma",
    "institucion": "institución",
    "indicador_economico": "indicador económico",
    "periodo": "período",
    "materia_cambiaria": "materia cambiaria",
}
INVERSO = {v: k for k, v in PROMPTS_NATURALES.items()}

#: Tipos de norma con un término propio en el texto, y el término esperado.
#: «Documento normativo» queda fuera: es la categoría genérica y no permite
#: comprobar nada.
TERMINOS = {
    "Resolución": ["resoluc"],
    "Circular": ["circular"],
    "Convenio cambiario": ["convenio"],
    "Decreto": ["decreto"],
    "Ley": ["ley"],
    "Aviso oficial": ["aviso"],
}

#: Formas que deberían detectarse. Salen del propio dominio del BCV; se buscan
#: en el corpus y se comprueba si cada motor las encuentra.
FORMAS = [
    ("materia_cambiaria", "operadores cambiarios"),
    ("materia_cambiaria", "casas de cambio"),
    ("materia_cambiaria", "mesas de cambio"),
    ("materia_cambiaria", "mercado cambiario"),
    ("tipo_de_norma", "resoluciones"),
    ("tipo_de_norma", "leyes"),
    ("tipo_de_norma", "decretos"),
    ("tipo_de_norma", "circulares"),
    ("moneda", "bolívares"),
    ("moneda", "dólares"),
    ("moneda", "euros"),
    ("institucion", "bancos universales"),
    ("sistema_de_pago", "transferencias"),
    ("indicador_economico", "tipo de cambio"),
]


def cargar_chunks() -> list[dict]:
    ruta = settings.PROCESSED_DIR / "chunks.jsonl"
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}. Ejecuta antes: python -m src.chunking")
    salida = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        c = json.loads(linea)
        if len((c.get("texto") or "").strip()) < MIN_CARACTERES:
            continue
        salida.append(c)
    return salida


def construir_muestra(chunks: list[dict], n: int, por_tipo: int = 15, por_forma: int = 15):
    """Muestra que garantiza datos para las tres pruebas."""
    rnd = random.Random(42)
    elegidos: dict[str, dict] = {}

    def anadir(c):
        elegidos[c["doc_id"] + "#" + str(c.get("chunk_index")) + c.get("seccion", "")] = c

    # (a) fragmentos de cada tipo de norma con término propio
    por_tipo_map = collections.defaultdict(list)
    for c in chunks:
        t = c.get("tipo_norma")
        if t in TERMINOS:
            por_tipo_map[t].append(c)
    for t, lista in por_tipo_map.items():
        rnd.shuffle(lista)
        for c in lista[:por_tipo]:
            anadir(c)

    # (b) fragmentos que contienen cada forma morfológica
    for _etiqueta, forma in FORMAS:
        hallados = [c for c in chunks if forma in (c.get("texto") or "").lower()]
        rnd.shuffle(hallados)
        for c in hallados[:por_forma]:
            anadir(c)

    # (c) relleno aleatorio hasta n
    resto = chunks[:]
    rnd.shuffle(resto)
    for c in resto:
        if len(elegidos) >= n:
            break
        anadir(c)

    return list(elegidos.values())[:n]


def motor_regex(texto: str) -> list[str]:
    return ner._regex_entities(texto)


def motor_gliner(modelo, texto: str, naturales: bool = False) -> list[str]:
    """Entidades según GLiNER.

    Con `naturales=True` las etiquetas se le pasan escritas en español normal y
    la salida se normaliza al nombre canónico, para que las métricas sean
    comparables entre las dos formas de preguntar.
    """
    etiquetas = [PROMPTS_NATURALES[c] for c in settings.LEGAL_ENTITY_LABELS] if naturales \
        else settings.LEGAL_ENTITY_LABELS
    ents = modelo.predict_entities(texto[:4000], etiquetas, threshold=settings.NER_THRESHOLD)
    salida = []
    for e in ents:
        et = INVERSO.get(e["label"], e["label"]) if naturales else e["label"]
        salida.append(f"{et}:{e['text'].strip().lower()}")
    return list(dict.fromkeys(salida))


#: Etiquetas de vocabulario cerrado: para ellas la lista de valores válidos es
#: finita y conocida, así que un valor fuera de la lista es una variante que las
#: reglas pierden o un error. `institucion` se queda fuera: sus valores son
#: abiertos por naturaleza.
CERRADAS = {
    "tipo_de_norma", "moneda", "sistema_de_pago",
    "indicador_economico", "instrumento_financiero", "materia_cambiaria", "periodo",
}

def vocabulario_de_reglas(salidas: list[list[str]]) -> dict[str, set[str]]:
    """Valores que el motor de reglas produce de hecho.

    Es más fiable que deducir la lista leyendo la expresión regular: la salida
    del propio motor es, por definición, exactamente su vocabulario.
    """
    vocab: dict[str, set[str]] = collections.defaultdict(set)
    for lista in salidas:
        for e in lista:
            et, _, v = e.partition(":")
            vocab[et].add(v)
    return vocab


def contiene(entidades: list[str], etiqueta: str, tallo: str) -> bool:
    """¿Hay alguna entidad de esa etiqueta cuyo valor contenga el tallo?"""
    for e in entidades:
        et, _, v = e.partition(":")
        if et == etiqueta and tallo in v:
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Compara motores de NER")
    ap.add_argument("--muestra", type=int, default=500)
    args = ap.parse_args()

    chunks = cargar_chunks()
    muestra = construir_muestra(chunks, args.muestra)
    print(f"Corpus: {len(chunks)} fragmentos útiles · muestra: {len(muestra)}\n")

    print(f"Cargando GLiNER: {settings.NER_MODEL} …", flush=True)
    from gliner import GLiNER

    t0 = time.time()
    modelo = GLiNER.from_pretrained(settings.NER_MODEL)
    print(f"  cargado en {time.time() - t0:.1f} s\n")

    motores = {
        "reglas": motor_regex,
        "GLiNER": lambda t: motor_gliner(modelo, t, naturales=False),
        "GLiNER-nat": lambda t: motor_gliner(modelo, t, naturales=True),
    }
    salidas: dict[str, list[list[str]]] = {k: [] for k in motores}
    tiempos: dict[str, float] = {k: 0.0 for k in motores}

    t0 = time.time()
    for i, c in enumerate(muestra, 1):
        texto = c.get("texto") or ""
        for nombre, fn in motores.items():
            t1 = time.time()
            salidas[nombre].append(fn(texto))
            tiempos[nombre] += time.time() - t1
        if i % 50 == 0:
            print(f"  {i}/{len(muestra)} · {time.time() - t0:.0f} s", flush=True)

    # Combinaciones
    salidas["unión"] = [
        list(dict.fromkeys(a + b + c))
        for a, b, c in zip(salidas["reglas"], salidas["GLiNER"], salidas["GLiNER-nat"])
    ]
    # Reglas para vocabulario cerrado + GLiNER solo para las etiquetas abiertas.
    # Se prueba con las dos formas de etiquetar.
    for base, destino in (("GLiNER", "combinado"), ("GLiNER-nat", "combinado-nat")):
        salidas[destino] = [
            list(dict.fromkeys(
                [e for e in r if e.split(":", 1)[0] in CERRADAS]
                + [e for e in g if e.split(":", 1)[0] not in CERRADAS]
            ))
            for r, g in zip(salidas["reglas"], salidas[base])
        ]

    nombres = ["reglas", "GLiNER", "GLiNER-nat", "unión", "combinado", "combinado-nat"]

    # ---------------- Volumen ----------------
    print("\n" + "=" * 74)
    print("1. VOLUMEN DE ENTIDADES")
    print("=" * 74)
    print(f"{'Motor':<14}{'frags con ≥1':>14}{'% cobertura':>13}{'entidades/frag':>16}{'distintas':>11}")
    for n in nombres:
        con = sum(1 for e in salidas[n] if e)
        total = sum(len(e) for e in salidas[n])
        distintas = len({x for e in salidas[n] for x in e})
        print(f"{n:<14}{con:>14}{con * 100 / len(muestra):>12.1f}%{total / len(muestra):>16.1f}{distintas:>11}")

    # ---------------- Recall contra metadatos ----------------
    print("\n" + "=" * 74)
    print("2. RECALL DE `tipo_de_norma` CONTRA LOS METADATOS DEL CORPUS")
    print("=" * 74)
    print("   El tipo de norma de cada fragmento es un dato de la ingesta, no del NER.")
    print("   «techo» = fragmentos cuyo texto contiene el término (nadie puede más).\n")
    print(f"{'Tipo':<22}{'n':>5}{'techo':>8}" + "".join(f"{m:>12}" for m in nombres) + f"{'det/techo':>12}")
    for tipo, tallos in TERMINOS.items():
        idx = [i for i, c in enumerate(muestra) if c.get("tipo_norma") == tipo]
        if not idx:
            continue
        techo = [i for i in idx
                 if any(t in (muestra[i].get("texto") or "").lower() for t in tallos)]
        fila = f"{tipo:<22}{len(idx):>5}{len(techo):>8}"
        tasas = {}
        for n in nombres:
            det = sum(1 for i in techo if any(contiene(salidas[n][i], "tipo_de_norma", t) for t in tallos))
            tasas[n] = det / len(techo) if techo else 0
            fila += f"{det / len(techo) * 100 if techo else 0:>11.0f}%"
        fila += f"{tasas['combinado'] * 100:>11.0f}%"
        print(fila)

    # ---------------- Morfología ----------------
    print("\n" + "=" * 74)
    print("3. COBERTURA MORFOLÓGICA (formas que deberían detectarse)")
    print("=" * 74)
    print(f"{'Forma esperada':<28}{'etiqueta':<20}{'n':>5}" + "".join(f"{m:>11}" for m in nombres))
    total_formas = {n: 0 for n in nombres}
    de_formas = 0
    for etiqueta, forma in FORMAS:
        idx = [i for i, c in enumerate(muestra) if forma in (c.get("texto") or "").lower()]
        if not idx:
            continue
        de_formas += 1
        fila = f"{forma:<28}{etiqueta:<20}{len(idx):>5}"
        for n in nombres:
            aciertos = sum(1 for i in idx if contiene(salidas[n][i], etiqueta, forma.split()[-1][:7]))
            total_formas[n] += aciertos
            fila += f"{aciertos / len(idx) * 100:>10.0f}%"
        print(fila)
    total_idx = sum(len([i for i, c in enumerate(muestra) if f in (c.get("texto") or "").lower()])
                    for _e, f in FORMAS)
    if total_idx:
        media = " · ".join(f"{n} {total_formas[n] * 100 / total_idx:.0f}%" for n in nombres)
        print(f"\n  Media ponderada de las {de_formas} formas presentes: {media}")

    # ---------------- Morfología, comprobación literal ----------------
    print("\n" + "=" * 74)
    print("3b. ¿SE CAPTURA LA FORMA EXACTA? (no otra entidad de la misma etiqueta)")
    print("=" * 74)
    print("   Aquí se exige que el valor contenga la forma tal cual está escrita.")
    print("   Es la prueba directa del plural: `operador cambiario` no es")
    print("   `operadores cambiarios`, y `ley` no es `leyes`.\n")
    claves = ["reglas", "GLiNER", "GLiNER-nat"]
    print(f"{'Forma':<28}{'n':>5}" + "".join(f"{m:>13}" for m in claves))
    total = {m: 0 for m in claves}
    n_idx = 0
    for etiqueta, forma in FORMAS:
        idx = [i for i, c in enumerate(muestra) if forma in (c.get("texto") or "").lower()]
        if not idx:
            continue
        n_idx += len(idx)
        fila = f"{forma:<28}{len(idx):>5}"
        for m in claves:
            aciertos = sum(
                1 for i in idx
                if any(e.startswith(etiqueta + ":") and forma in e for e in salidas[m][i])
            )
            total[m] += aciertos
            fila += f"{aciertos / len(idx) * 100:>12.0f}%"
        print(fila)
    if n_idx:
        print("\n  Total: " + " · ".join(f"{m} {total[m] * 100 / n_idx:.0f}%" for m in claves))

    # ---------------- Ruido ----------------
    print("\n" + "=" * 74)
    print("4. VALORES FUERA DEL VOCABULARIO CONOCIDO (posible ruido o variantes perdidas)")
    print("=" * 74)
    vocab = vocabulario_de_reglas(salidas["reglas"])
    for etiqueta in sorted(CERRADAS):
        conocidos = vocab.get(etiqueta, set())
        veces: collections.Counter = collections.Counter()
        for lista in salidas["GLiNER"]:
            for e in lista:
                et, _, v = e.partition(":")
                if et != etiqueta:
                    continue
                # Se compara por contención en ambos sentidos para no marcar como
                # novedad una simple variante de longitud («tipo de cambio» frente
                # a «tipo de cambio oficial»).
                if not any(clave in v or v in clave for clave in conocidos):
                    veces[v] += 1
        if not veces:
            continue
        print(f"\n  {etiqueta}")
        for v, k in veces.most_common(8):
            print(f"     {k:>5}  {v[:70]}")

    # ---------------- Tiempo ----------------
    print("\n" + "=" * 74)
    print("5. TIEMPO")
    print("=" * 74)
    for n in ("reglas", "GLiNER", "GLiNER-nat"):
        por_frag = tiempos[n] / len(muestra)
        print(f"  {n:<10}{por_frag * 1000:>8.0f} ms/fragmento   "
              f"→ {por_frag * len(chunks) / 60:>5.1f} min para los {len(chunks)} del corpus")

    destino = RAIZ / "data" / "processed" / "informe_ner.json"
    destino.write_text(json.dumps({
        "muestra": len(muestra),
        "cobertura": {n: sum(1 for e in salidas[n] if e) / len(muestra) for n in nombres},
        "entidades_por_fragmento": {n: sum(len(e) for e in salidas[n]) / len(muestra) for n in nombres},
        "tiempos_ms": {n: tiempos[n] / len(muestra) * 1000 for n in ("reglas", "GLiNER", "GLiNER-nat")},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Informe → {destino}")


if __name__ == "__main__":
    main()
