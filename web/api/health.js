/** GET /api/health — estado del modo nativo de Vercel. */
import { totalFragmentos } from './_lib/corpus.js'
import { preflight } from './_lib/http.js'

export default function handler(req, res) {
  if (preflight(req, res)) return

  return res.status(200).json({
    status: 'ok',
    modo: 'vercel-serverless',
    motor: 'bm25',
    coleccion: 'Normativa',
    objetos: totalFragmentos(),
  })
}
