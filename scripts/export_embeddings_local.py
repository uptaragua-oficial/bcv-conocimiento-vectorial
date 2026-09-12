"""Vectoriza el corpus en local con un modelo de sentence-transformers.

**Reanudable:** guarda el avance lote a lote, así que un corte de luz, un
reinicio o un Ctrl-C solo cuestan el último lote, no todo el trabajo. Al
volver a ejecutarlo continúa donde quedó.

No depende de ninguna API (ni claves, ni restricciones geográficas). El
proveedor externo solo hace falta luego, en tiempo de ejecución, para
vectorizar la consulta — y debe servir el mismo modelo.

Uso:
  python -m scripts.export_embeddings_local            # continúa si había avance
  python -m scripts.export_embeddings_local --reiniciar

Variables:
  EMBED_MODEL        modelo (por defecto intfloat/multilingual-e5-large)
  EMBED_PREFIJO_DOC  prefijo de los documentos (por defecto "passage: ")
  EMBED_PREFIJO_Q    prefijo de las consultas (por defecto "query: ")
  EMBED_FORMATO      formato del proveedor en ejecución: huggingface | openai
  EMBED_URL          URL de embeddings del proveedor (opcional)
  EMBED_LOTE         tamaño de lote (por defecto 16)

Escribe `web/api/_data/vectors.f32` y `embeddings_meta.json`. La meta incluye el
formato y el prefijo de consulta, de modo que la función de Vercel se configura
sola a partir de ella.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CORPUS = RAIZ / "web" / "api" / "_data" / "corpus.json"
DESTINO = RAIZ / "web" / "api" / "_data" / "vectors.f32"
META = RAIZ / "web" / "api" / "_data" / "embeddings_meta.json"
# El avance vive en data/processed (ignorado por git)
AVANCE = RAIZ / "data" / "processed" / "embeddings_avance.json"

MODELO = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")
PREFIJO_DOC = os.getenv("EMBED_PREFIJO_DOC", "passage: ")
PREFIJO_Q = os.getenv("EMBED_PREFIJO_Q", "query: ")
FORMATO = os.getenv("EMBED_FORMATO", "huggingface")
LOTE = int(os.getenv("EMBED_LOTE", "16"))


def _url_por_defecto(modelo: str, formato: str) -> str:
    if formato == "huggingface":
        return f"https://router.huggingface.co/hf-inference/models/{modelo}"
    return os.getenv("EMBED_URL", "")


def _leer_avance() -> int:
    """Cuántos vectores ya están escritos y son válidos."""
    if not (AVANCE.exists() and DESTINO.exists()):
        return 0
    try:
        datos = json.loads(AVANCE.read_text(encoding="utf-8"))
        if datos.get("modelo") != MODELO or datos.get("dim") is None:
            return 0  # cambió el modelo: empezar de cero
        hechos = int(datos.get("hechos", 0))
        esperado = hechos * int(datos["dim"]) * 4
        if DESTINO.stat().st_size != esperado:
            print("  (el avance no cuadra con el archivo; se reinicia)")
            return 0
        return hechos
    except Exception:  # noqa: BLE001
        return 0


def run() -> dict:
    if not CORPUS.exists():
        raise SystemExit(
            f"No existe {CORPUS}. Ejecuta primero:\n  python -m scripts.export_vercel_index"
        )

    url = os.getenv("EMBED_URL") or _url_por_defecto(MODELO, FORMATO)
    docs = json.loads(CORPUS.read_text(encoding="utf-8"))["docs"]
    textos = [f"{PREFIJO_DOC}{d[6]}" for d in docs]
    total = len(textos)

    if "--reiniciar" in sys.argv:
        DESTINO.unlink(missing_ok=True)
        AVANCE.unlink(missing_ok=True)

    hechos = _leer_avance()
    if hechos:
        print(
            f"Reanudando: {hechos}/{total} vectores ya calculados "
            f"(se conservan; solo se calcula el resto)"
        )
    else:
        DESTINO.unlink(missing_ok=True)
        META.unlink(missing_ok=True)  # no dejar una meta que no corresponda
        hechos = 0
        print(f"Vectorizando {total} fragmentos con {MODELO}")
        print(f"  prefijo documentos: {PREFIJO_DOC!r} · lote: {LOTE}")
        print("  El avance se guarda en cada lote: puedes interrumpir y continuar.\n")

    if hechos >= total:
        print("Ya estaba completo.")
    else:
        from sentence_transformers import SentenceTransformer

        modelo = SentenceTransformer(MODELO, device="cpu")
        dim = int(modelo.get_sentence_embedding_dimension())

        with DESTINO.open("ab") as f:
            for i in range(hechos, total, LOTE):
                lote = textos[i : i + LOTE]
                vecs = modelo.encode(
                    lote, batch_size=LOTE, normalize_embeddings=True, convert_to_numpy=True
                )
                f.write(vecs.astype("<f4").tobytes())
                f.flush()
                os.fsync(f.fileno())  # asegura el avance en disco
                hechos = i + len(lote)
                AVANCE.write_text(
                    json.dumps({"modelo": MODELO, "dim": dim, "hechos": hechos}),
                    encoding="utf-8",
                )
                print(f"  {hechos}/{total}", flush=True)

    # --- Meta final ---
    dim = int(DESTINO.stat().st_size / 4 / total)
    meta = {
        "n": total,
        "dim": dim,
        "modelo": MODELO,
        "formato": FORMATO,
        "prefijo_documento": PREFIJO_DOC,
        "prefijo_consulta": PREFIJO_Q,
        "url_sugerida": url,
        "normalizado": "l2",
        "origen": "calculado en local con sentence-transformers (sin API)",
        "generado": datetime.now(timezone.utc).isoformat(),
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    AVANCE.unlink(missing_ok=True)

    mb = DESTINO.stat().st_size / 1e6
    print(f"\nOK · {total} vectores de {dim} dims → {DESTINO} ({mb:.1f} MB)")
    print(f"Formato del proveedor: {FORMATO}")
    print(
        "\nEn Vercel basta con definir:\n"
        "  EMBEDDINGS_API_KEY = <clave del proveedor>\n"
        "El resto (modelo, URL y prefijo de consulta) se toma de embeddings_meta.json."
    )
    return meta


if __name__ == "__main__":
    run()
