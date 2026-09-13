/**
 * Cliente de embeddings para el modo nativo de Vercel.
 *
 * La consulta se vectoriza **en la función serverless** con una sola llamada
 * HTTP; los vectores del corpus se calcularon antes, fuera de línea, con el
 * mismo modelo (ver `scripts/export_embeddings_local.py`).
 *
 * Dos formatos de proveedor:
 *   * `openai`      → `POST {url}` con `{model, input}` y respuesta
 *                     `{data:[{embedding}]}`. Sirve para OpenAI, DeepInfra, Jina…
 *   * `huggingface` → `POST {url}` con `{inputs}` y respuesta `[[…]]`
 *                     (router de inferencia de HuggingFace).
 *
 * La configuración se deduce de `embeddings_meta.json`, así que en Vercel basta
 * con definir `EMBEDDINGS_API_KEY`. Cualquier variable de entorno explícita
 * tiene prioridad.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { claveDeEntorno } from './claves.js'

const AQUI = dirname(fileURLToPath(import.meta.url))
const RUTA_VECTORES = join(AQUI, '..', '_data', 'vectors.f32')
const RUTA_META = join(AQUI, '..', '_data', 'embeddings_meta.json')

let metaCache
let metaLeida = false

/** Meta de los vectores del corpus (o null si no se han generado). */
export function metaVectores() {
  if (!metaLeida) {
    metaLeida = true
    try {
      metaCache = JSON.parse(readFileSync(RUTA_META, 'utf-8'))
    } catch {
      metaCache = null
    }
  }
  return metaCache
}

/** Configuración del proveedor de embeddings, o null si no hay clave. */
export function embeddingsConfig() {
  const clave =
    claveDeEntorno('EMBEDDINGS_API_KEY') || claveDeEntorno('OPENAI_API_KEY')
  if (!clave) return null

  const meta = metaVectores()
  const formato = process.env.EMBEDDINGS_FORMATO || meta?.formato || 'openai'
  const modelo = process.env.EMBEDDINGS_MODEL || meta?.modelo || 'text-embedding-3-small'

  let url = process.env.EMBEDDINGS_URL || meta?.url_sugerida || ''
  if (!url) {
    const base = (process.env.EMBEDDINGS_BASE_URL || 'https://api.openai.com/v1').replace(/\/+$/, '')
    url = formato === 'huggingface' ? `${base}/models/${modelo}` : `${base}/embeddings`
  }

  const prefijo =
    process.env.EMBEDDINGS_PREFIJO_CONSULTA ?? meta?.prefijo_consulta ?? ''

  const cfg = { clave, url, modelo, formato, prefijo }
  if (process.env.EMBEDDINGS_DIMENSIONS) {
    cfg.dimensions = Number(process.env.EMBEDDINGS_DIMENSIONS)
  }
  return cfg
}

/** Normaliza a norma L2 (así el coseno es un producto punto). */
export function normalizarL2(v) {
  let suma = 0
  for (let i = 0; i < v.length; i++) suma += v[i] * v[i]
  const norma = Math.sqrt(suma) || 1
  const salida = new Float32Array(v.length)
  for (let i = 0; i < v.length; i++) salida[i] = v[i] / norma
  return salida
}

/** Vectoriza una consulta. Devuelve null si no hay proveedor configurado. */
export async function embeberConsulta(texto) {
  const cfg = embeddingsConfig()
  if (!cfg) return null

  const entrada = `${cfg.prefijo}${texto}`
  const esHF = cfg.formato === 'huggingface'

  const cuerpo = esHF ? { inputs: [entrada] } : { model: cfg.modelo, input: [entrada] }
  if (!esHF && cfg.dimensions) cuerpo.dimensions = cfg.dimensions

  const resp = await fetch(cfg.url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${cfg.clave}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(cuerpo),
  })
  if (!resp.ok) throw new Error(`embeddings HTTP ${resp.status}`)

  const datos = await resp.json()
  let vector
  if (esHF) {
    // [[...]] para una lista de entradas, [...] si el proveedor aplana
    vector = Array.isArray(datos?.[0]) ? datos[0] : datos
  } else {
    vector = datos?.data?.[0]?.embedding
  }
  if (!Array.isArray(vector) || typeof vector[0] !== 'number') {
    throw new Error('respuesta de embeddings sin vector')
  }
  return normalizarL2(Float32Array.from(vector))
}

let vectoresCache

/** Matriz de vectores del corpus como Float32Array plano (N × D). */
export function vectoresCorpus() {
  if (vectoresCache) return vectoresCache
  const meta = metaVectores()
  if (!meta) return null
  try {
    const buffer = readFileSync(RUTA_VECTORES)
    const plano = new Float32Array(
      buffer.buffer,
      buffer.byteOffset,
      Math.floor(buffer.byteLength / 4),
    )
    if (plano.length !== meta.n * meta.dim) {
      console.warn(
        `[embeddings] desajuste: ${plano.length} valores frente a ${meta.n}×${meta.dim}`,
      )
      return null
    }
    vectoresCache = { plano, n: meta.n, dim: meta.dim, meta }
    return vectoresCache
  } catch {
    return null
  }
}

/** ¿Está disponible la búsqueda semántica? (clave + vectores coherentes) */
export function semanticaDisponible() {
  const cfg = embeddingsConfig()
  if (!cfg) return false
  const v = vectoresCorpus()
  if (!v) return false
  if (cfg.dimensions && cfg.dimensions !== v.dim) return false
  if (cfg.modelo !== v.meta.modelo) {
    console.warn(
      `[embeddings] el modelo configurado (${cfg.modelo}) no coincide con el de los ` +
        `vectores (${v.meta.modelo}); se usará solo BM25`,
    )
    return false
  }
  return true
}
