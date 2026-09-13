/** GET /api/catalogo — valores de filtro y configuración activa del servicio. */
import { catalogoCorpus, totalFragmentos, vectoresAlineados } from './_lib/corpus.js'
import { proveedorLLM } from './_lib/rag.js'
import { embeddingsConfig, semanticaDisponible } from './_lib/embeddings.js'
import { rerankConfig, rerankDisponible } from './_lib/rerank.js'
import { preflight } from './_lib/http.js'

export default function handler(req, res) {
  if (preflight(req, res)) return

  const proveedor = proveedorLLM()
  const emb = embeddingsConfig()
  const rr = rerankConfig()
  // Se exige además que los vectores correspondan al corpus actual; si no, la
  // recuperación sería 'keyword' de todos modos.
  const semantica = semanticaDisponible() && vectoresAlineados()
  return res.status(200).json({
    ...catalogoCorpus(),
    generacion_llm: Boolean(proveedor),
    proveedor_llm: proveedor ? proveedor.nombre : null,
    modelo_llm: proveedor ? proveedor.modelo : null,
    recuperacion: semantica ? 'hibrida' : 'keyword',
    rerank: rerankDisponible(),
    modelo_rerank: rr ? rr.modelo : null,
    modelo_embeddings: emb ? emb.modelo : null,
    total_fragmentos: totalFragmentos(),
  })
}
