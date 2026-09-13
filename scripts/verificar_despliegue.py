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
import os
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


def peticion(
    url: str,
    metodo: str = "GET",
    cuerpo: dict | None = None,
    timeout: int = 45,
    cabeceras: dict | None = None,
):
    """Devuelve (codigo, datos) donde datos es el JSON o el texto crudo."""
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    pet = urllib.request.Request(url, data=datos, method=metodo)
    pet.add_header("Content-Type", "application/json")
    pet.add_header("Accept", "application/json")
    for k, v in (cabeceras or {}).items():
        pet.add_header(k, v)
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


def os_environ(nombre: str) -> str:
    return os.environ.get(nombre, "")


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


# ----------------------------------------------------------------------
# Prueba directa de claves (independiente del despliegue)
# ----------------------------------------------------------------------
def _explicar(codigo: int, proveedor: str) -> str:
    """Traduce un código HTTP al problema real, que casi nunca es el código."""
    return {
        401: f"clave ausente, inválida o sin permisos suficientes para {proveedor}",
        402: "la cuenta no tiene saldo",
        403: f"la clave no tiene permiso para usar {proveedor}",
        404: "el modelo no existe o tu cuenta no tiene acceso a él",
        422: "la petición no tiene el formato que espera el proveedor",
        429: "límite de uso alcanzado: espera un momento y reintenta",
        503: "el modelo está arrancando o no disponible en este momento",
    }.get(codigo, f"error HTTP {codigo}")


def _meta_local() -> dict:
    ruta = RAIZ / "web" / "api" / "_data" / "embeddings_meta.json"
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def probar_embeddings() -> bool:
    """Comprueba que el token de Hugging Face devuelve un vector del tamaño correcto."""
    meta = _meta_local()
    clave = (os_environ("EMBEDDINGS_API_KEY") or os_environ("OPENAI_API_KEY") or "").strip()
    print("  Embeddings")
    if not clave:
        fallo(
            "EMBEDDINGS_API_KEY no está definida en esta terminal",
            "expórtala para probarla aquí; en Vercel debe estar en Environment Variables",
        )
        return False

    url = os_environ("EMBEDDINGS_URL") or meta.get("url_sugerida") or ""
    modelo = os_environ("EMBEDDINGS_MODEL") or meta.get("modelo") or ""
    formato = meta.get("formato", "huggingface")
    prefijo = meta.get("prefijo_consulta", "")
    dim = int(meta.get("dim") or 0)
    print(color(f"    modelo: {modelo} · formato: {formato}", GRIS))
    print(color(f"    prefijo de consulta: {prefijo!r}", GRIS))

    cuerpo = {"inputs": [f"{prefijo}prueba de configuración"]}
    if formato != "huggingface":
        cuerpo = {"model": modelo, "input": [f"{prefijo}prueba de configuración"]}

    codigo, datos = peticion(url, metodo="POST", cuerpo=cuerpo, cabeceras={"Authorization": f"Bearer {clave}"})
    if codigo == 0:
        fallo(f"No se pudo conectar con {url}", str(datos)[:160])
        return False
    if codigo != 200:
        fallo(f"El proveedor de embeddings respondió HTTP {codigo}", _explicar(codigo, "Inference Providers"))
        print(color(f"    respuesta: {str(datos)[:200]}", GRIS))
        return False

    vector = datos[0] if isinstance(datos, list) and datos and isinstance(datos[0], list) else datos
    if not isinstance(vector, list) or not vector or not isinstance(vector[0], (int, float)):
        fallo("La respuesta no contiene un vector", str(datos)[:200])
        return False
    if dim and len(vector) != dim:
        fallo(
            f"El vector tiene {len(vector)} dimensiones y los del corpus {dim}",
            "El modelo configurado no es el mismo con el que se vectorizó el corpus",
        )
        return False
    ok(f"Token válido: devuelve un vector de {len(vector)} dimensiones")
    return True


def probar_rerank() -> bool:
    """Comprueba el proveedor de rerank con una petición mínima."""
    print("\n  Rerank")
    url = (os_environ("RERANK_API_URL") or "").strip()
    clave = (os_environ("RERANK_API_KEY") or "").strip()
    if not url:
        aviso("RERANK_API_URL no está definida: el portal no reordenará")
        return False

    # Mismo criterio que el cliente del portal (web/api/_lib/rerank.js): cada
    # proveedor tiene su catálogo y mandar el modelo de otro da un 404 confuso.
    bajo = url.lower()
    es_deepinfra = "deepinfra.com" in bajo or "/inference" in bajo
    por_defecto = (
        "Qwen/Qwen3-Reranker-0.6B" if es_deepinfra
        else "jina-reranker-v3.5" if "jina.ai" in bajo
        else "BAAI/bge-reranker-v2-m3"
    )
    modelo = (os_environ("RERANK_MODEL") or por_defecto).strip()
    destino = url.rstrip("/")
    if es_deepinfra:
        if "{model}" in destino:
            destino = destino.replace("{model}", modelo)
        elif not destino.split("/inference")[-1].strip("/"):
            destino = f"{destino}/{modelo}"
        cuerpo = {"queries": ["prueba"], "documents": ["documento uno", "documento dos"]}
    else:
        cuerpo = {"model": modelo, "query": "prueba",
                  "documents": ["documento uno", "documento dos"], "top_n": 2}
    print(color(f"    modelo: {modelo}", GRIS))

    print(color(f"    endpoint: {destino}", GRIS))
    codigo, datos = peticion(destino, metodo="POST", cuerpo=cuerpo, cabeceras={"Authorization": f"Bearer {clave}"})
    if codigo == 0:
        fallo(f"No se pudo conectar con el proveedor de rerank", str(datos)[:160])
        return False
    if codigo != 200:
        fallo(f"El proveedor de rerank respondió HTTP {codigo}", _explicar(codigo, "DeepInfra"))
        print(color(f"    respuesta: {str(datos)[:200]}", GRIS))
        return False

    puntajes = datos.get("scores") if isinstance(datos, dict) else None
    if puntajes is None and isinstance(datos, dict):
        puntajes = datos.get("results")
    if not puntajes:
        fallo("La respuesta no contiene puntajes", str(datos)[:200])
        return False
    ok(f"Proveedor operativo: devolvió {len(puntajes)} puntaje(s)")
    return True


def probar_llm() -> bool:
    """Comprueba la clave del LLM con una petición mínima."""
    print("\n  LLM")
    for nombre, var, defecto in (
        ("deepseek", "DEEPSEEK_API_KEY", "https://api.deepseek.com"),
        ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    ):
        clave = (os_environ(var) or "").strip()
        if not clave:
            continue
        base = (os_environ(var.replace("_API_KEY", "_BASE_URL")) or defecto).rstrip("/")
        modelo = os_environ(var.replace("_API_KEY", "_MODEL")) or (
            "deepseek-flash" if nombre == "deepseek" else "openai/gpt-oss-120b"
        )
        codigo, datos = peticion(
            f"{base}/chat/completions",
            metodo="POST",
            cuerpo={"model": modelo, "messages": [{"role": "user", "content": "hola"}], "max_tokens": 1},
            cabeceras={"Authorization": f"Bearer {clave}"},
        )
        if codigo == 200:
            ok(f"{nombre} operativo ({modelo})")
            return True
        fallo(f"{nombre} respondió HTTP {codigo}", _explicar(codigo, nombre))
        print(color(f"    respuesta: {str(datos)[:200]}", GRIS))
        return False

    aviso("Sin clave de LLM: el portal responderá en modo extractivo (es válido)")
    return False


def revisar_claves() -> int:
    """Prueba las claves de esta terminal contra los proveedores reales."""
    print("\nPrueba directa de claves (no depende del despliegue)")
    print(color("  Se leen de las variables de entorno de ESTA terminal.\n", GRIS))
    resultados = [probar_embeddings(), probar_rerank(), probar_llm()]
    print("\n" + "─" * 68)
    if all(resultados[:2]):
        print(color("  Las dos claves críticas funcionan: el despliegue debería dar híbrida + rerank.", VERDE))
    else:
        print(color("  Alguna clave no funciona todavía. El detalle está arriba.", AMARILLO))
    print()
    return 0 if all(resultados[:2]) else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Verifica un despliegue del portal")
    ap.add_argument("base", nargs="?", default="http://localhost:3001", help="URL base")
    ap.add_argument(
        "--claves",
        action="store_true",
        help="prueba las claves de esta terminal contra los proveedores, sin consultar el despliegue",
    )
    args = ap.parse_args()

    if args.claves:
        raise SystemExit(revisar_claves())
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
