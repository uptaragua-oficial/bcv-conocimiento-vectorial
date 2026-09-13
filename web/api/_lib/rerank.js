/**
 * Reordenación (rerank) de los candidatos con un cross-encoder.
 *
 * **Por qué no se ejecuta el modelo aquí.** `BAAI/bge-reranker-v2-m3` pesa
 * 2,2 GB en fp32 y el límite de una función serverless de Vercel es 250 MB sin
 * comprimir. Además un cross-encoder hay que evaluarlo en CPU, sin GPU, para
 * cada par (consulta, fragmento): con 30 candidatos el coste por consulta es
 * inasumible dentro de los 30 s de `maxDuration`.
 *
 * **Cómo funciona entonces.** El rerank se delega en un proveedor externo, con
 * el formato estándar de la industria (Jina, Cohere, Voyage, TEI…):
 *
 *   POST {url}
 *   { "model": "...", "query": "...", "documents": ["...", "..."], "top_n": 5 }
 *   → { "results": [ { "index": 3, "relevance_score": 0.87 }, … ] }
 *
 * El `index` es la posición en el arreglo `documents` que se envió, así que se
 * usa para reordenar los candidatos originales.
 *
 * **El rerank es opcional.** Si no hay proveedor configurado o la llamada falla,
 * se devuelve el orden original: el portal sigue funcionando con la fusión
 * híbrida o con BM25. Nunca lanza.
 *
 * Variables de entorno:
 *   RERANK_API_URL     endpoint del proveedor (obligatoria para activarlo)
 *   RERANK_API_KEY     clave del proveedor
 *   RERANK_MODEL       modelo (por defecto BAAI/bge-reranker-v2-m3)
 *   RERANK_CANDIDATOS  candidatos a recuperar antes de reordenar (por defecto 30)
 *   RERANK_ACTIVO      "false" lo desactiva aunque haya proveedor
 */

/** Recorta el texto enviado al proveedor: acota coste y latencia. */
const MAX_CARACTERES = 2000

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

  const candidatos = Number(process.env.RERANK_CANDIDATOS || 30)
  return {
    url,
    clave: (process.env.RERANK_API_KEY || '').trim(),
    modelo: (process.env.RERANK_MODEL || 'BAAI/bge-reranker-v2-m3').trim(),
    candidatos: Number.isFinite(candidatos) ? Math.min(Math.max(candidatos, 10), 100) : 30,
  }
}

/** ¿Hay un proveedor de rerank utilizable? */
export function rerankDisponible() {
  if (process.env.RERANK_ACTIVO === 'false') return false
  return rerankConfig() !== null
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
      body: JSON.stringify({
        model: cfg.modelo,
        query: consulta,
        documents: documentos,
        top_n: limit,
      }),
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

  // El formato estándar devuelve `results`; algunos proveedores anidan en `data`.
  const resultados = Array.isArray(datos?.results)
    ? datos.results
    : Array.isArray(datos?.data)
      ? datos.data
      : null
  if (!resultados) {
    console.warn('[rerank] respuesta sin resultados')
    return items
  }

  const ordenados = []
  for (const r of resultados) {
    const i = Number(r?.index)
    if (!Number.isInteger(i) || i < 0 || i >= items.length) continue
    ordenados.push({ ...items[i], rerank_score: Number(r?.relevance_score ?? r?.score ?? 0) })
  }
  if (!ordenados.length) return items

  // Si el proveedor devolvió menos de `top_n`, se completan los que faltaban
  // conservando su orden original, para no perder candidatos.
  if (ordenados.length < limit) {
    const vistos = new Set(resultados.map((r) => Number(r?.index)))
    for (let i = 0; i < items.length && ordenados.length < limit; i++) {
      if (!vistos.has(i)) ordenados.push(items[i])
    }
  }
  return ordenados.slice(0, limit)
}
