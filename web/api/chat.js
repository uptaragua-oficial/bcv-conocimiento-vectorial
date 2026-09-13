/**
 * GET/POST /api/chat — asistente conversacional (modo nativo de Vercel).
 *
 * Recupera con búsqueda híbrida (BM25 + embeddings cuando están disponibles),
 * compone la respuesta con citas y, si hay proveedor de LLM, la redacta.
 * El campo `recuperacion` indica qué estrategia se usó.
 */
import { buscarHibrido, ALPHA_POR_DEFECTO } from './_lib/corpus.js'
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
  const alpha = p.alpha === undefined ? ALPHA_POR_DEFECTO : Number(p.alpha)
  // El rerank se activa si el llamador lo pide; si no lo menciona, se aplica
  // cuando hay proveedor configurado (RERANK_API_URL).
  const rerank = p.rerank === undefined ? undefined : p.rerank === true || p.rerank === 'true'
  const t0 = Date.now()

  try {
    const { resultados, modo, rerank: aplicado } = await buscarHibrido(mensaje, {
      limit,
      filtros,
      alpha,
      rerank,
    })
    const salida = await chat({ mensaje, resultados, historial: p.historial })
    return res.status(200).json({
      ...salida,
      recuperacion: modo,
      alpha: modo.startsWith('hibrida') ? alpha : null,
      rerank: Boolean(aplicado),
      latencia_ms: Date.now() - t0,
    })
  } catch (e) {
    return res.status(503).json({ detail: `Error del asistente: ${e.message}` })
  }
}
