/** GET/POST /api/search — recuperación BM25 con filtros (modo nativo de Vercel). */
import { buscarCorpus } from './_lib/corpus.js'
import { preflight, parametros, normalizarFiltros } from './_lib/http.js'

export default function handler(req, res) {
  if (preflight(req, res)) return

  const p = parametros(req)
  const query = String(p.query || p.q || '').trim()
  if (!query) {
    return res.status(422).json({ detail: 'Falta el parámetro query' })
  }

  const limit = Math.min(Math.max(Number(p.limit) || 5, 1), 50)
  const filtros = normalizarFiltros(p.filtros)
  const t0 = Date.now()

  try {
    const resultados = buscarCorpus(query, { limit, filtros })
    return res.status(200).json({
      query,
      modo: 'keyword',
      n: resultados.length,
      latencia_ms: Date.now() - t0,
      resultados,
    })
  } catch (e) {
    return res.status(503).json({ detail: `Error de búsqueda: ${e.message}` })
  }
}
