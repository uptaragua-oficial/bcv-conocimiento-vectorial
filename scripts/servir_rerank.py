"""Sirve el cross-encoder de rerank como API, con el **formato estándar**.

Para qué sirve
--------------
El portal desplegado en Vercel no puede ejecutar el modelo (2,2 GB frente al
límite de 250 MB de la función, y 16 s por consulta en CPU). Este script lo
ejecuta **en tu máquina**, con la GPU si la hay, y lo expone por HTTP con el
mismo formato que hablan Jina, Cohere o Voyage:

    POST /rerank
    { "query": "...", "documents": ["…"], "top_n": 5 }
    → { "results": [ { "index": 3, "relevance_score": 0.87 }, … ] }

Como el cliente del portal (`web/api/_lib/rerank.js`) ya habla ese formato, **no
hay que cambiar ni una línea del portal**: basta con apuntar `RERANK_API_URL` a
la URL pública de este servidor.

Uso
---
    # 1) En tu máquina (con la GPU si está disponible)
    python -m scripts.servir_rerank --puerto 8090

    # 2) En otra terminal, un túnel para que Vercel pueda alcanzarlo
    cloudflared tunnel --url http://127.0.0.1:8090

    # 3) En Vercel → Environment Variables
    RERANK_API_URL=https://<lo-que-imprima-cloudflared>/rerank
    RERANK_API_KEY=  (no hace falta; el servidor no pide clave)

Variables:
  RERANK_MODEL    modelo a servir (por defecto BAAI/bge-reranker-v2-m3)
  RERANK_DEVICE   cpu | cuda (por defecto, automático)
  HF_HOME         caché de modelos (por defecto, la del proyecto si existe)
"""
from __future__ import annotations

import argparse
import os
import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field

RAIZ = Path(__file__).resolve().parent.parent

#: Recorte del texto, igual que en el cliente del portal. Acota el cómputo por
#: par sin perder nada: los fragmentos del corpus no llegan a ese tamaño.
MAX_CARACTERES = 2000

class PeticionRerank(BaseModel):
    """Cuerpo de la petición, en el formato estándar de rerank.

    Se declara a nivel de módulo a propósito: con `from __future__ import
    annotations` las anotaciones son cadenas y FastAPI las resuelve contra los
    globales del módulo. Una clase definida dentro de una función no se
    encontraría y FastAPI interpretaría el cuerpo como un parámetro de consulta.
    """

    query: str = Field(..., description="Consulta del usuario.")
    documents: list[str] = Field(..., description="Fragmentos candidatos.")
    top_n: int | None = Field(None, description="Cuántos devolver.")
    model: str | None = Field(None, description="Ignorado: el modelo lo fija el servidor.")


_cerrojo = threading.Lock()
_modelo = None
_dispositivo = None
_carga_s = None


def _preparar_entorno() -> None:
    """Reutiliza la caché de modelos del proyecto si existe.

    Sin esto, `sentence-transformers` mira en `~/.cache/huggingface`, donde puede
    haber un token caducado que provoca un 401 al descargar el modelo.
    """
    if os.getenv("HF_HOME"):
        return
    candidata = Path("/home/upta/DeepSeekHarness/upta/.rag-cache/hf")
    if candidata.is_dir():
        os.environ["HF_HOME"] = str(candidata)


def cargar_modelo():
    global _modelo, _dispositivo, _carga_s
    if _modelo is not None:
        return _modelo
    with _cerrojo:
        if _modelo is not None:
            return _modelo
        _preparar_entorno()
        from sentence_transformers import CrossEncoder

        nombre = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
        dispositivo = os.getenv("RERANK_DEVICE") or ""
        if not dispositivo:
            try:
                import torch

                dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:  # noqa: BLE001
                dispositivo = "cpu"

        t0 = time.time()
        print(f"[rerank] cargando {nombre} en {dispositivo}…", flush=True)
        _modelo = CrossEncoder(nombre, device=dispositivo, max_length=512)
        _dispositivo = dispositivo
        _carga_s = time.time() - t0
        print(f"[rerank] listo en {_carga_s:.1f} s", flush=True)
        return _modelo


def main() -> None:
    ap = argparse.ArgumentParser(description="Sirve el cross-encoder de rerank")
    ap.add_argument("--host", default="127.0.0.1", help="interfaz de escucha")
    ap.add_argument("--puerto", type=int, default=8090)
    ap.add_argument("--lote", type=int, default=16)
    ap.add_argument(
        "--precargar",
        action="store_true",
        help="carga el modelo antes de aceptar peticiones (recomendado con túnel)",
    )
    args = ap.parse_args()

    from fastapi import FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="BCV · Servicio de rerank",
        description="Cross-encoder local con el formato estándar de rerank.",
        version="1.0.0",
    )
    # El portal se sirve desde otro dominio (Vercel), así que el navegador
    # necesita permiso explícito para llamar aquí.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "servicio": "rerank",
            "modelo": os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
            "dispositivo": _dispositivo or "sin cargar",
            "carga_s": _carga_s,
        }

    @app.post("/rerank")
    def rerank(p: PeticionRerank, authorization: str | None = Header(None)):
        # Si se define RERANK_API_KEY, se exige; así el túnel no queda abierto a
        # cualquiera. El cliente del portal ya envía la cabecera cuando la tiene.
        esperada = (os.getenv("RERANK_API_KEY") or "").strip()
        if esperada:
            recibida = (authorization or "").removeprefix("Bearer ").strip()
            if recibida != esperada:
                raise HTTPException(status_code=401, detail="clave incorrecta")

        if not p.documents:
            return {"results": []}
        modelo = cargar_modelo()
        documentos = [d[:MAX_CARACTERES] for d in p.documents]

        t0 = time.time()
        pares = [(p.query, d) for d in documentos]
        # El modelo no es seguro para uso concurrente: se serializa.
        with _cerrojo:
            puntajes = modelo.predict(pares, batch_size=args.lote, show_progress_bar=False)
        ms = (time.time() - t0) * 1000

        orden = sorted(range(len(puntajes)), key=lambda i: -float(puntajes[i]))
        if p.top_n:
            orden = orden[: p.top_n]
        print(
            f"[rerank] {len(documentos)} documentos en {ms:.0f} ms"
            f" ({'cuda' if _dispositivo == 'cuda' else 'cpu'})",
            flush=True,
        )
        return {
            "results": [
                {"index": i, "relevance_score": float(puntajes[i]), "document": {"text": documentos[i]}}
                for i in orden
            ]
        }

    if args.precargar:
        cargar_modelo()

    import uvicorn

    print(f"\n[rerank] escuchando en http://{args.host}:{args.puerto}")
    print(f"[rerank] endpoint para Vercel → RERANK_API_URL=<url-publica>/rerank\n")
    uvicorn.run(app, host=args.host, port=args.puerto, log_level="warning")


if __name__ == "__main__":
    main()
