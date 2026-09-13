/**
 * GET/POST /api/search — recuperación híbrida (BM25 + embeddings) con filtros.
 *
 * Si hay proveedor de embeddings y vectores del corpus, fusiona lo léxico y lo
 * semántico con `alpha` (1 = solo semántico, 0 = solo BM25). Si no, responde
 * con BM25 y lo indica en `modo`.
 */
import { buscarHibrido, ALPHA_POR_DEFECTO } from './_lib/corpus.js'
import { preflight, parametros, normalizarFiltros } from './_lib/http.js'

export default async function handler(req, res) {
  if (preflight(req, res)) return

  const p = parametros(req)
  const query = String(p.query || p.q || '').trim()
  if (!query) {
    return res.status(422).json({ detail: 'Falta el parámetro query' })
  }

  const limit = Math.min(Math.max(Number(p.limit) || 5, 1), 50)
  const filtros = normalizarFiltros(p.filtros)
  const alpha = p.alpha === undefined ? ALPHA_POR_DEFECTO : Number(p.alpha)
  const rerank = p.rerank === undefined ? undefined : p.rerank === true || p.rerank === 'true'
  const t0 = Date.now()

  try {
    const { resultados, modo, rerank: aplicado } = await buscarHibrido(query, {
      limit,
      filtros,
      alpha,
      rerank,
    })
    return res.status(200).json({
      query,
      modo,
      alpha: modo.startsWith('hibrida') ? alpha : null,
      rerank: Boolean(aplicado),
      n: resultados.length,
      latencia_ms: Date.now() - t0,
      resultados,
    })
  } catch (e) {
    return res.status(503).json({ detail: `Error de búsqueda: ${e.message}` })
  }
}
