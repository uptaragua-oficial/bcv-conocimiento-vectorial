/**
 * Reordenación (rerank) de los candidatos con un cross-encoder.
 *
 * **Por qué no se ejecuta el modelo aquí.** `BAAI/bge-reranker-v2-m3` pesa
 * 2,2 GB en fp32 y el límite de una función serverless de Vercel es 250 MB sin
 * comprimir. Además un cross-encoder hay que evaluarlo en CPU, sin GPU, para
 * cada par (consulta, fragmento): con 20 candidatos son 16 s por consulta,
 * medidos. No cabe.
 *
 * **Dos formatos de proveedor.** No todos hablan el mismo dialecto:
 *
 *   * `estandar`  → el de Jina, Cohere, Voyage y Text Embeddings Inference:
 *
 *       POST {url}
 *       { "model": "...", "query": "...", "documents": ["…"], "top_n": 5 }
 *       → { "results": [ { "index": 3, "relevance_score": 0.87 }, … ] }
 *
 *     Devuelve `index` (la posición en `documents`) y ya viene ordenado.
 *
 *   * `deepinfra` → propio de DeepInfra:
 *
 *       POST https://api.deepinfra.com/v1/inference/{modelo}
 *       { "queries": ["..."], "documents": ["…"] }
 *       → { "scores": [0.94, 0.0001, …], "input_tokens": 348 }
 *
 *     El modelo va **en la URL**, `queries` es un arreglo, y `scores` viene
 *     **en el mismo orden que `documents` y sin ordenar**: hay que ordenarlo
 *     aquí. No admite `top_n`.
 *
 * El formato se deduce de la URL (o se fuerza con `RERANK_FORMATO`).
 *
 * **El rerank es opcional.** Si no hay proveedor configurado o la llamada falla,
 * se devuelve el orden original: el portal sigue funcionando con la fusión
 * híbrida o con BM25. Nunca lanza.
 *
 * Variables de entorno:
 *   RERANK_API_URL     endpoint del proveedor (obligatoria para activarlo)
 *   RERANK_API_KEY     clave del proveedor
 *   RERANK_FORMATO     auto | estandar | deepinfra   (por defecto: auto)
 *   RERANK_MODEL       modelo (por defecto: bge-reranker-v2-m3, o
 *                      Qwen3-Reranker-0.6B si el proveedor es DeepInfra)
 *   RERANK_CANDIDATOS  candidatos a recuperar antes de reordenar (por defecto 30)
 *   RERANK_ACTIVO      "false" lo desactiva aunque haya proveedor
 *   RERANK_INSTRUCTION solo DeepInfra: instrucción que orienta la tarea
 */

/** Recorta el texto enviado al proveedor: acota coste y latencia. */
const MAX_CARACTERES = 2000

/** Modelo por defecto de cada formato. */
const MODELO_POR_DEFECTO = {
  estandar: 'BAAI/bge-reranker-v2-m3',
  deepinfra: 'Qwen/Qwen3-Reranker-0.6B',
}

/**
 * Deduce el dialecto a partir de la URL.
 *
 * DeepInfra expone `POST /v1/inference/{modelo}`; el resto de proveedores usan
 * un endpoint fijo con el modelo en el cuerpo.
 */
export function detectarFormato(valor, url) {
  const explicito = (valor || '').trim().toLowerCase()
  if (explicito === 'estandar' || explicito === 'deepinfra') return explicito
  // `/inference` puede venir sin barra final (…/v1/inference) o con el modelo
  // ya pegado (…/v1/inference/Qwen/Qwen3-Reranker-8B).
  return /deepinfra\.com|\/inference(\/|$)/i.test(url || '') ? 'deepinfra' : 'estandar'
}

/**
 * Resuelve la URL final y el modelo.
 *
 * En DeepInfra el modelo forma parte de la ruta. Se admiten las tres formas:
 *   …/inference/Qwen/Qwen3-Reranker-8B   (modelo en la URL)
 *   …/inference/{model}                  (marcador a sustituir)
 *   …/inference                          (se añade el de RERANK_MODEL)
 */
function resolverDestino(url, formato, modeloPedido) {
  const limpia = url.replace(/\/+$/, '')
  if (limpia.includes('{model}')) {
    return { url: limpia.replace('{model}', modeloPedido), modelo: modeloPedido }
  }
  if (formato === 'deepinfra') {
    const enRuta = limpia.match(/\/inference\/(.+)$/i)
    if (enRuta) return { url: limpia, modelo: enRuta[1] }
    return { url: `${limpia}/${modeloPedido}`, modelo: modeloPedido }
  }
  return { url: limpia, modelo: modeloPedido }
}

/**
 * Configuración del proveedor de rerank, o null si no está configurado.
 *
 * Se lee del entorno en cada llamada (no se cachea) para que las pruebas puedan
 * activar y desactivar el proveedor sin reiniciar el proceso. El coste es
 * despreciable frente a la llamada HTTP que viene después.
 */
export function rerankConfig() {
  const url = (process.env.RERANK_API_URL || '').trim()
  if (!url) return null

  const formato = detectarFormato(process.env.RERANK_FORMATO, url)
  const modeloPedido = (process.env.RERANK_MODEL || MODELO_POR_DEFECTO[formato]).trim()
  const { url: destino, modelo } = resolverDestino(url, formato, modeloPedido)

  const candidatos = Number(process.env.RERANK_CANDIDATOS || 30)
  return {
    url: destino,
    modelo,
    formato,
    clave: (process.env.RERANK_API_KEY || '').trim(),
    candidatos: Number.isFinite(candidatos) ? Math.min(Math.max(candidatos, 10), 100) : 30,
    instruccion: (process.env.RERANK_INSTRUCTION || '').trim(),
  }
}

/** ¿Hay un proveedor de rerank utilizable? */
export function rerankDisponible() {
  if (process.env.RERANK_ACTIVO === 'false') return false
  return rerankConfig() !== null
}

/** Cuerpo de la petición según el dialecto del proveedor. */
function cuerpoPeticion(cfg, consulta, documentos, limit) {
  if (cfg.formato === 'deepinfra') {
    // `queries` es un arreglo y una sola consulta se reparte entre todos los
    // documentos. No hay `top_n`: se pide todo y se recorta aquí.
    const cuerpo = { queries: [consulta], documents: documentos }
    if (cfg.instruccion) cuerpo.instruction = cfg.instruccion
    return cuerpo
  }
  return { model: cfg.modelo, query: consulta, documents: documentos, top_n: limit }
}

/**
 * Extrae los puntajes de la respuesta y los devuelve **alineados con `items`**.
 *
 * @returns {number[]|null} un puntaje por candidato, o null si no se pudo leer.
 */
function leerPuntajes(cfg, datos, n) {
  // DeepInfra: `scores` va en el mismo orden que `documents`, sin ordenar.
  if (cfg.formato === 'deepinfra') {
    const scores = datos?.scores
    if (!Array.isArray(scores) || scores.length !== n) return null
    return scores.map(Number)
  }

  // Estándar: `results` trae `index` y `relevance_score`, ya ordenado y
  // posiblemente recortado a `top_n`. Los ausentes quedan al final.
  const resultados = Array.isArray(datos?.results)
    ? datos.results
    : Array.isArray(datos?.data)
      ? datos.data
      : null
  if (!resultados) return null
  const puntajes = new Array(n).fill(-Infinity)
  let leidos = 0
  for (const r of resultados) {
    const i = Number(r?.index)
    if (!Number.isInteger(i) || i < 0 || i >= n) continue
    puntajes[i] = Number(r?.relevance_score ?? r?.score ?? 0)
    leidos++
  }
  return leidos ? puntajes : null
}

/**
 * Reordena `items` según su relevancia real para `consulta`.
 *
 * @param {string} consulta
 * @param {Array<{texto:string}>} items  candidatos ya recuperados, en orden
 * @param {{limit?:number}} opciones
 * @returns {Promise<Array>} los mismos objetos, reordenados y recortados.
 *   Si el rerank no está disponible o falla, devuelve `items` tal cual.
 */
export async function reordenar(consulta, items, opciones = {}) {
  const cfg = rerankConfig()
  if (!cfg || process.env.RERANK_ACTIVO === 'false') return items
  if (!Array.isArray(items) || items.length < 2) return items

  const limit = Math.min(Math.max(opciones.limit || 5, 1), 50)
  const documentos = items.map((it) => (it.texto || '').slice(0, MAX_CARACTERES))

  const cabeceras = { 'Content-Type': 'application/json' }
  if (cfg.clave) cabeceras.Authorization = `Bearer ${cfg.clave}`

  let resp
  try {
    resp = await fetch(cfg.url, {
      method: 'POST',
      headers: cabeceras,
      body: JSON.stringify(cuerpoPeticion(cfg, consulta, documentos, limit)),
    })
  } catch (e) {
    console.warn(`[rerank] no se pudo contactar al proveedor: ${e.message}`)
    return items
  }

  if (!resp.ok) {
    let detalle = ''
    try {
      detalle = (await resp.text()).slice(0, 200)
    } catch {
      /* sin cuerpo legible */
    }
    console.warn(`[rerank] HTTP ${resp.status}${detalle ? ` · ${detalle}` : ''}`)
    return items
  }

  let datos
  try {
    datos = await resp.json()
  } catch {
    console.warn('[rerank] respuesta ilegible')
    return items
  }

  const puntajes = leerPuntajes(cfg, datos, items.length)
  if (!puntajes) {
    console.warn('[rerank] respuesta sin puntajes utilizables')
    return items
  }

  return items
    .map((item, i) => ({ ...item, rerank_score: puntajes[i] }))
    .sort((a, b) => b.rerank_score - a.rerank_score)
    .slice(0, limit)
}
