/**
 * Servidor de embeddings simulado (compatible con OpenAI) para desarrollo.
 *
 * Permite probar la búsqueda híbrida **sin gastar créditos** ni necesitar una
 * clave real. Genera vectores deterministas por bolsa de palabras: los textos
 * con vocabulario parecido quedan cerca, suficiente para validar la plomería.
 *
 * Uso:
 *   node scripts/mock-embeddings.mjs            # puerto 9999, 8 dims
 *   DIM=64 PORT=9999 node scripts/mock-embeddings.mjs
 *
 * Luego, para vectorizar el corpus contra él:
 *   EMBEDDINGS_API_KEY=test \
 *   EMBEDDINGS_BASE_URL=http://127.0.0.1:9999/v1 \
 *   EMBEDDINGS_MODEL=mock-model \
 *   python -m scripts.export_openai_embeddings
 */
import { createServer } from 'node:http'

const DIM = Number(process.env.DIM || 8)
const PUERTO = Number(process.env.PORT || 9999)

function vector(texto) {
  const v = new Array(DIM).fill(0)
  const tokens =
    String(texto || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .match(/[a-z0-9]{3,}/g) || []
  for (const t of tokens) {
    let h = 0
    for (const c of t) h = (h * 31 + c.charCodeAt(0)) >>> 0
    v[h % DIM] += 1
  }
  return v
}

createServer(async (req, res) => {
  let cuerpo = ''
  for await (const trozo of req) cuerpo += trozo

  let entrada = []
  try {
    const datos = JSON.parse(cuerpo || '{}')
    entrada = Array.isArray(datos.input) ? datos.input : [datos.input]
  } catch {
    res.statusCode = 400
    return res.end(JSON.stringify({ error: 'JSON inválido' }))
  }

  res.setHeader('Content-Type', 'application/json')
  res.end(
    JSON.stringify({
      object: 'list',
      model: 'mock-embeddings',
      data: entrada.map((texto, index) => ({ object: 'embedding', index, embedding: vector(texto) })),
      usage: { prompt_tokens: 0, total_tokens: 0 },
    }),
  )
}).listen(PUERTO, () => {
  console.log(`Embeddings simulados en http://127.0.0.1:${PUERTO}/v1/embeddings (${DIM} dims)`)
})
