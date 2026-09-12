/** GET/POST /api/chat — asistente conversacional (modo nativo de Vercel). */
import { buscarCorpus } from './_lib/corpus.js'
import { chat } from './_lib/rag.js'
import { preflight, parametros, normalizarFiltros } from './_lib/http.js'

export default async function handler(req, res) {
  if (preflight(req, res)) return

  if (req.method !== 'POST' && req.method !== 'GET') {
    return res.status(405).json({ detail: 'Método no permitido' })
  }

  const p = parametros(req)
  const mensaje = String(p.mensaje || p.q || '').trim()
  if (mensaje.length < 2) {
    return res.status(422).json({ detail: 'El mensaje debe tener al menos 2 caracteres' })
  }

  const limit = Math.min(Math.max(Number(p.limit) || 5, 1), 10)
  const filtros = normalizarFiltros(p.filtros)
  const t0 = Date.now()

  try {
    const resultados = buscarCorpus(mensaje, { limit, filtros })
    const salida = await chat({ mensaje, resultados, historial: p.historial })
    return res.status(200).json({ ...salida, latencia_ms: Date.now() - t0 })
  } catch (e) {
    return res.status(503).json({ detail: `Error del asistente: ${e.message}` })
  }
}
