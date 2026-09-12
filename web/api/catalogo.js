/** GET /api/catalogo — valores disponibles para los filtros. */
import { catalogoCorpus, totalFragmentos } from './_lib/corpus.js'
import { preflight } from './_lib/http.js'

export default function handler(req, res) {
  if (preflight(req, res)) return

  return res.status(200).json({
    ...catalogoCorpus(),
    generacion_llm: Boolean(process.env.GROQ_API_KEY),
    total_fragmentos: totalFragmentos(),
  })
}
