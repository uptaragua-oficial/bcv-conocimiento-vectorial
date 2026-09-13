"""Diagnostica por qué falla la llamada al modelo de lenguaje.

Comprueba la clave configurada (formato, espacios sobrantes) y hace una llamada
real, mostrando **el mensaje exacto** que devuelve el proveedor. Con eso se
distingue entre clave inválida, modelo inexistente, falta de saldo o país
bloqueado.

Uso:
  python -m scripts.diagnosticar_llm                 # usa DEEPSEEK_API_KEY del entorno
  python -m scripts.diagnosticar_llm --groq          # prueba Groq
  python -m scripts.diagnosticar_llm --clave sk-...  # clave suelta (queda en el historial)

Si no hay clave en el entorno, la pide de forma oculta.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

# Valores por defecto alineados con src/rag.py
PROVEEDORES = {
    "deepseek": {
        "clave_env": "DEEPSEEK_API_KEY",
        "url": "https://api.deepseek.com",
        "modelo": "deepseek-flash",
    },
    "groq": {
        "clave_env": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1",
        "modelo": "openai/gpt-oss-120b",
    },
}


def _cargar_env() -> None:
    """Lee .env si existe, para reproducir lo que ve el portal."""
    from pathlib import Path

    ruta = Path(__file__).resolve().parent.parent / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, _, v = linea.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def _revisar_clave(nombre: str, clave: str) -> list[str]:
    """Problemas detectables sin llamar a la API."""
    problemas = []
    if clave != clave.strip():
        problemas.append("tiene espacios o saltos de línea al principio o al final")
    if " " in clave.strip() or "\n" in clave:
        problemas.append("contiene espacios o saltos de línea en medio")
    if not clave.strip().startswith("sk-"):
        problemas.append("no empieza por 'sk-'; ¿copiaste el identificador en vez de la clave?")
    if len(clave.strip()) < 20:
        problemas.append(f"es sospechosamente corta ({len(clave.strip())} caracteres)")
    if clave.strip().lower().startswith("bearer "):
        problemas.append("incluye el prefijo 'Bearer ', que ya se añade automáticamente")
    return problemas


def diagnosticar(nombre: str, clave: str, modelo: str | None, url: str) -> bool:
    cfg = PROVEEDORES[nombre]
    limpia = clave.strip()

    print(f"Proveedor : {nombre}")
    print(f"Clave    : {limpia[:6]}…{limpia[-4:]} ({len(limpia)} caracteres)")
    print(f"Modelo   : {modelo}")

    problemas = _revisar_clave(nombre, clave)
    if problemas:
        print("\nAvisos sobre la clave:")
        for p in problemas:
            print(f"  · {p}")
        print("  → El portal ya recorta los espacios, pero conviene corregirla igualmente.")
    else:
        print("\nFormato de la clave: correcto")

    endpoint = f"{url.rstrip('/')}/chat/completions"
    print(f"\nLlamando a {endpoint} …")

    payload = {
        "model": modelo,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "Responde solo: OK"}],
    }
    if nombre == "deepseek":
        payload["thinking"] = {"type": "disabled"}

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {limpia}", "Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            datos = json.loads(r.read())
        texto = (datos.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        print(f"\nÉXITO · el modelo respondió: {texto!r}")
        print("La clave es válida. Si el portal falla, revisa que la variable esté")
        print("definida en el entorno correcto de Vercel y que hayas REDESPLEGADO.")
        return True
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")
        print(f"\nFALLO · HTTP {e.code}")
        print(f"Respuesta del proveedor: {cuerpo[:400]}")
        print()
        if e.code == 401:
            print("  401 → la clave no es válida o está revocada.")
            print("        Genera una nueva en el panel del proveedor.")
        elif e.code == 402:
            print("  402 → sin saldo en la cuenta.")
        elif e.code == 404:
            print(f"  404 → el modelo '{modelo}' no existe o tu cuenta no tiene acceso.")
            print("        Prueba con DEEPSEEK_MODEL=deepseek-flash o deepseek-v4-pro.")
        elif e.code == 403:
            print("  403 → prohibido: puede ser un bloqueo por país/región.")
        elif e.code == 429:
            print("  429 → demasiadas peticiones; espera un momento.")
        return False
    except urllib.error.URLError as e:
        print(f"\nFALLO de red: {e.reason}")
        print("Puede ser un bloqueo por país: prueba a ejecutarlo desde otra red.")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Diagnostica la clave del modelo de lenguaje")
    ap.add_argument("--clave", help="clave a probar (si no, se toma del entorno)")
    ap.add_argument("--modelo", help="modelo a usar")
    ap.add_argument("--groq", action="store_true", help="probar Groq en vez de DeepSeek")
    args = ap.parse_args()

    _cargar_env()
    nombre = "groq" if args.groq else "deepseek"
    cfg = PROVEEDORES[nombre]

    clave = args.clave or os.getenv(cfg["clave_env"]) or ""
    if not clave:
        from getpass import getpass

        print(f"No hay {cfg['clave_env']} en el entorno.")
        clave = getpass(f"Pega la clave de {nombre}: ")
    if not clave:
        raise SystemExit("Sin clave no se puede diagnosticar.")

    modelo = (
        args.modelo
        or os.getenv(f"{nombre.upper()}_MODEL")
        or cfg["modelo"]
    )
    url = os.getenv(f"{nombre.upper()}_BASE_URL") or cfg["url"]

    ok = diagnosticar(nombre, clave, modelo, url)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
