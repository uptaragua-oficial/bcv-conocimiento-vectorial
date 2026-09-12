/** GET /api/catalogo — valores de filtro y configuración activa del servicio. */
import { catalogoCorpus, totalFragmentos } from './_lib/corpus.js'
import { proveedorLLM } from './_lib/rag.js'
import { embeddingsConfig, semanticaDisponible } from './_lib/embeddings.js'
import { preflight } from './_lib/http.js'

export default function handler(req, res) {
  if (preflight(req, res)) return

  const proveedor = proveedorLLM()
  const emb = embeddingsConfig()
  return res.status(200).json({
    ...catalogoCorpus(),
    generacion_llm: Boolean(proveedor),
    proveedor_llm: proveedor ? proveedor.nombre : null,
    modelo_llm: proveedor ? proveedor.modelo : null,
    // Recuperación: 'hibrida' si hay embeddings y vectores; si no, 'keyword'.
    recuperacion: semanticaDisponible() ? 'hibrida' : 'keyword',
    modelo_embeddings: emb ? emb.modelo : null,
    total_fragmentos: totalFragmentos(),
  })
}
