"""Verifica un despliegue del portal (Vercel o backend propio) de una sola pasada.

Hace lo que uno haría a mano —`curl` al health, una consulta de prueba y mirar si
aparece el artículo correcto— pero comprobando **cada pieza por separado**, de
modo que si algo falla se sabe qué variable falta y no solo que "no funciona".

Uso:
  python -m scripts.verificar_despliegue https://mi-app.vercel.app
  python -m scripts.verificar_despliegue            # por defecto, local

Solo usa la biblioteca estándar: se puede ejecutar en cualquier máquina sin
instalar nada.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Consulta de referencia y texto que identifica el artículo que debe aparecer.
#: Es la consulta real que motivó la lematización y el rerank: si el Art. 12 del
#: Convenio Cambiario N.º 1 no está entre los cinco primeros, la recuperación del
#: portal no está bien configurada.
CONSULTA_REFERENCIA = "¿Qué requisitos exige el BCV para ser operador cambiario autorizado?"
MARCADOR_ESPERADO = "Quedan autorizados para actuar"

VERDE, ROJO, AMARILLO, GRIS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"


def color(texto: str, tono: str) -> str:
    return f"{tono}{texto}{FIN}" if sys.stdout.isatty() else texto


def ok(texto: str) -> None:
    print(f"  {color('✔', VERDE)} {texto}")


def fallo(texto: str, arreglo: str = "") -> None:
    print(f"  {color('✘', ROJO)} {texto}")
    if arreglo:
        print(f"      {color('→ ' + arreglo, AMARILLO)}")


def aviso(texto: str) -> None:
    print(f"  {color('•', AMARILLO)} {texto}")


def peticion(url: str, metodo: str = "GET", cuerpo: dict | None = None, timeout: int = 45):
    """Devuelve (codigo, datos) donde datos es el JSON o el texto crudo."""
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    pet = urllib.request.Request(url, data=datos, method=metodo)
    pet.add_header("Content-Type", "application/json")
    pet.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(pet, timeout=timeout) as r:
            crudo = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(crudo)
            except json.JSONDecodeError:
                return r.status, crudo
    except urllib.error.HTTPError as e:
        crudo = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(crudo)
        except json.JSONDecodeError:
            return e.code, crudo
    except urllib.error.URLError as e:
        return 0, str(e.reason)
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def corpus_local() -> int | None:
    """Fragmentos del corpus de este repositorio, para comparar con lo desplegado."""
    ruta = RAIZ / "web" / "api" / "_data" / "corpus.json"
    try:
        return len(json.loads(ruta.read_text(encoding="utf-8"))["docs"])
    except Exception:  # noqa: BLE001
        return None


def revisar_modo_nativo(base: str, salud: dict) -> list[str]:
    """Revisa un despliegue en modo nativo de Vercel. Devuelve los problemas."""
    problemas = []

    # --- Corpus ---
    objetos = salud.get("objetos")
    esperado = corpus_local()
    if objetos is None:
        fallo("El health no informa del número de fragmentos")
        problemas.append("health")
    elif esperado is not None and objetos != esperado:
        fallo(
            f"El corpus desplegado tiene {objetos} fragmentos y el del repositorio {esperado}",
            "Vercel está sirviendo una versión anterior: vuelve a desplegar la rama main",
        )
        problemas.append("corpus")
    else:
        ok(f"Corpus: {objetos} fragmentos")

    # --- Vectores ---
    v = salud.get("vectores")
    if not v:
        fallo(
            "No hay vectores del corpus en el despliegue",
            "Faltan web/api/_data/vectors.f32 y embeddings_meta.json en el repositorio",
        )
        problemas.append("vectores")
    elif not v.get("alineados"):
        fallo(
            f"Vectores desalineados: {v.get('n')} vectores para {objetos} fragmentos",
            "Re-vectoriza y vuelve a desplegar (ver docs/VECTORIZAR.md)",
        )
        problemas.append("vectores")
    else:
        ok(f"Vectores alineados: {v['n']} × {v['dim']} ({v['modelo']})")

    # --- Búsqueda semántica ---
    if salud.get("recuperacion") == "hibrida":
        ok(f"Búsqueda híbrida activa (embeddings: {salud.get('embeddings_modelo')})")
    else:
        fallo(
            "La búsqueda semántica NO está activa: el portal responde solo con BM25",
            "Falta EMBEDDINGS_API_KEY en Vercel (token de Hugging Face, empieza por hf_)",
        )
        problemas.append("embeddings")

    # --- Rerank ---
    if salud.get("rerank"):
        cfg = salud.get("rerank_config") or {}
        ok(f"Rerank activo ({cfg.get('modelo')}, {cfg.get('candidatos')} candidatos)")
    else:
        fallo(
            "El rerank NO está activo",
            "Falta RERANK_API_URL en Vercel (ver docs/PROVEEDORES-RERANK.md)",
        )
        problemas.append("rerank")

    # --- Clave del LLM ---
    llm = salud.get("llm") or {}
    if not llm.get("configurado"):
        aviso("Sin proveedor de LLM: el portal responde en modo extractivo (es válido)")
    elif not llm.get("clave_prefijo_valido", True):
        fallo(
            f"La clave de {llm.get('proveedor')} no empieza por "
            f"{llm.get('clave_prefijo_esperado')!r} (longitud: {llm.get('clave_longitud')})",
            "Corrige la clave en Vercel: es el error más común al pegarla",
        )
        problemas.append("llm")
    else:
        ok(f"LLM configurado: {llm.get('proveedor')} · {llm.get('modelo')}")

    return problemas


def revisar_modo_backend(base: str, salud: dict) -> list[str]:
    """Revisa un backend propio (FastAPI + Weaviate)."""
    problemas = []
    if salud.get("weaviate"):
        ok("Weaviate disponible")
    else:
        fallo("Weaviate no responde", "Comprueba el contenedor y WEAVIATE_HOST/PORT")
        problemas.append("weaviate")
    ok(f"Colección: {salud.get('collection')} · modelo: {salud.get('embedding_model')}")
    return problemas


def prueba_funcional(base: str, es_nativo: bool, salud: dict) -> tuple[bool, list[str]]:
    """Comprueba que la consulta de referencia devuelve el artículo correcto.

    Además contrasta lo que **declara** el health con lo que **ocurrió** en la
    consulta. El health informa de la configuración, no de si funciona: un token
    de embeddings inválido o un proveedor de rerank que rechaza la petición
    dejan el portal degradado sin que el health cambie. Esa discrepancia es la
    causa de la mayoría de las horas perdidas, así que se comprueba aquí.
    """
    extra: list[str] = []
    print("\nPrueba funcional")
    print(color(f"  consulta: {CONSULTA_REFERENCIA}", GRIS))
    ruta = "/api/search" if es_nativo else "/search"
    codigo, datos = peticion(
        f"{base}{ruta}",
        metodo="POST",
        cuerpo={"query": CONSULTA_REFERENCIA, "limit": 5},
    )
    if codigo != 200 or not isinstance(datos, dict):
        fallo(f"La búsqueda falló (HTTP {codigo})", str(datos)[:200])
        return False, extra

    resultados = datos.get("resultados") or []
    modo = datos.get("modo", "?")
    rerank = datos.get("rerank")
    print(color(f"  modo: {modo} · rerank: {rerank} · {len(resultados)} resultados", GRIS))

    # --- Configurado pero no funcionando ---
    if es_nativo:
        if salud.get("recuperacion") == "hibrida" and modo != "hibrida":
            fallo(
                "La búsqueda semántica figura como activa, pero la consulta cayó a BM25",
                "El token de embeddings está puesto pero la llamada falla: comprueba "
                "que tenga permiso de Inference Providers y que no esté caducado",
            )
            extra.append("embeddings-no-responde")
        if salud.get("rerank") and rerank is False:
            fallo(
                "El rerank figura como activo, pero el proveedor no lo aplicó",
                "Revisa RERANK_API_KEY y RERANK_API_URL (mira los registros de la función)",
            )
            extra.append("rerank-no-responde")

    puesto = None
    for i, r in enumerate(resultados, 1):
        if MARCADOR_ESPERADO.lower() in (r.get("texto") or "").lower():
            puesto = i
            break

    if puesto:
        ok(f"El Art. 12 del Convenio Cambiario N.º 1 aparece en el puesto {puesto}")
        return True, extra

    fallo(
        f"El Art. 12 NO aparece en el top-5 (debería decir «{MARCADOR_ESPERADO}»)",
        "Con embeddings y rerank activos queda 3.º; sin ellos es lo esperado",
    )
    print(color("      lo que devolvió:", GRIS))
    for i, r in enumerate(resultados, 1):
        linea = f"      {i}. {r.get('seccion', '?')} · {r.get('titulo', '')[:50]}"
        print(color(linea, GRIS))
    return False, extra


def main() -> None:
    ap = argparse.ArgumentParser(description="Verifica un despliegue del portal")
    ap.add_argument("base", nargs="?", default="http://localhost:3001", help="URL base")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print(f"\nVerificando {color(base, GRIS)}\n")

    codigo, salud = peticion(f"{base}/api/health")
    if codigo == 0:
        print(f"  {color('✘', ROJO)} No se pudo conectar: {salud}")
        print(color("    → revisa la URL y que el despliegue esté listo", AMARILLO))
        raise SystemExit(1)
    if codigo != 200 or not isinstance(salud, dict):
        print(f"  {color('✘', ROJO)} /api/health devolvió HTTP {codigo}")
        print(f"    {str(salud)[:300]}")
        raise SystemExit(1)

    print("Estado del servicio")
    es_nativo = salud.get("modo") == "vercel-serverless"
    if es_nativo:
        problemas = revisar_modo_nativo(base, salud)
    else:
        ok(f"Backend en línea ({salud.get('collection', 'colección desconocida')})")
        problemas = revisar_modo_backend(base, salud)

    funcional, extra = prueba_funcional(base, es_nativo, salud)
    problemas.extend(extra)

    print("\n" + "─" * 68)
    if not problemas and funcional:
        print(color("  Todo correcto: el despliegue está completo y responde bien.", VERDE))
    else:
        print(color(f"  Quedan {len(problemas)} ajuste(s) de configuración.", AMARILLO))
        for p in problemas:
            print(f"    · {p}")
        if not funcional:
            print("    · la consulta de referencia no encuentra el artículo esperado")
    print()

    raise SystemExit(0 if (not problemas and funcional) else 1)


if __name__ == "__main__":
    main()
