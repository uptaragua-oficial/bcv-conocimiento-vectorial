/**
 * Cliente de embeddings (API compatible con OpenAI) para el modo nativo.
 *
 * La consulta se vectoriza **en la función serverless** con una sola llamada
 * HTTP; los vectores del corpus se calcularon antes, fuera de línea, con el
 * mismo modelo (ver `scripts/export_openai_embeddings.py`). Solo coinciden si
 * el modelo y las dimensiones son los mismos: por eso se validan contra la
 * meta guardada junto a los vectores.
 *
 * Compatible con OpenAI, DeepInfra, Jina, Voyage… (todos exponen
 * `POST /embeddings` con el formato de OpenAI).
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const AQUI = dirname(fileURLToPath(import.meta.url))
const RUTA_VECTORES = join(AQUI, '..', '_data', 'vectors.f32')
const RUTA_META = join(AQUI, '..', '_data', 'embeddings_meta.json')

/** Configuración del proveedor de embeddings, o null si no hay clave. */
export function embeddingsConfig() {
  const clave = process.env.EMBEDDINGS_API_KEY || process.env.OPENAI_API_KEY
  if (!clave) return null
  const base = (process.env.EMBEDDINGS_BASE_URL || 'https://api.openai.com/v1').replace(/\/+$/, '')
  const cfg = {
    clave,
    url: `${base}/embeddings`,
    modelo: process.env.EMBEDDINGS_MODEL || 'text-embedding-3-small',
  }
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

  const payload = { model: cfg.modelo, input: [texto] }
  if (cfg.dimensions) payload.dimensions = cfg.dimensions

  const resp = await fetch(cfg.url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${cfg.clave}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(`embeddings HTTP ${resp.status}`)
  const datos = await resp.json()
  const vector = datos?.data?.[0]?.embedding
  if (!Array.isArray(vector)) throw new Error('respuesta de embeddings sin vector')
  return normalizarL2(Float32Array.from(vector))
}

let metaCache = null

/** Meta de los vectores del corpus (o null si no se han generado). */
export function metaVectores() {
  if (metaCache !== undefined && metaCache !== null) return metaCache
  try {
    metaCache = JSON.parse(readFileSync(RUTA_META, 'utf-8'))
  } catch {
    metaCache = null
  }
  return metaCache
}

let vectoresCache = null

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
  // Si se fijó una dimensionalidad, debe coincidir con la de los vectores.
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
