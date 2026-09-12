/**
 * Carga perezosa del corpus, del índice BM25 y de los vectores del corpus
 * (modo nativo de Vercel). Todo se construye una sola vez por instancia.
 *
 * Ofrece dos niveles de recuperación:
 *   * `buscarCorpus`  → BM25 (léxico), siempre disponible.
 *   * `buscarHibrido` → BM25 + similitud coseno, si hay proveedor de
 *                       embeddings configurado y vectores del corpus.
 *
 * El corpus se lee con `fs` para que Vercel lo incluya en el bundle de la
 * función (ver `includeFiles` en vercel.json).
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { construir, buscar, puntajesBm25, mejores, catalogo } from './bm25.js'
import { embeberConsulta, semanticaDisponible, vectoresCorpus } from './embeddings.js'

const AQUI = dirname(fileURLToPath(import.meta.url))
const RUTA_CORPUS = join(AQUI, '..', '_data', 'corpus.json')

let datos = null
let indice = null

function getDatos() {
  if (!datos) {
    datos = JSON.parse(readFileSync(RUTA_CORPUS, 'utf-8'))
  }
  return datos
}

export function getIndice() {
  if (!indice) {
    const t0 = Date.now()
    indice = construir(getDatos().docs)
    console.log(`[corpus] índice BM25 listo: ${indice.n} fragmentos en ${Date.now() - t0} ms`)
  }
  return indice
}

export function buscarCorpus(consulta, opciones) {
  return buscar(getIndice(), consulta, opciones)
}

/** Similitud coseno de la consulta contra todos los fragmentos. */
function puntajesCoseno(indice, vectorConsulta) {
  const v = vectoresCorpus()
  if (!v) return null
  const { plano, dim } = v
  if (vectorConsulta.length !== dim) return null

  const scores = new Float64Array(indice.n)
  for (let i = 0; i < indice.n; i++) {
    let suma = 0
    const base = i * dim
    for (let d = 0; d < dim; d++) suma += plano[base + d] * vectorConsulta[d]
    scores[i] = suma > 0 ? suma : 0 // el coseno negativo no aporta
  }
  return scores
}

/** Normaliza unos puntajes respecto al máximo (para fusionar escalas). */
function normalizar(scores) {
  let max = 0
  for (let i = 0; i < scores.length; i++) if (scores[i] > max) max = scores[i]
  if (max <= 0) return scores
  const salida = new Float64Array(scores.length)
  for (let i = 0; i < scores.length; i++) salida[i] = scores[i] / max
  return salida
}

/**
 * Búsqueda híbrida con fusión lineal: `alpha` pondera lo semántico y
 * `1 - alpha` lo léxico. Si no hay embeddings disponibles, cae a BM25.
 */
export async function buscarHibrido(consulta, opciones = {}) {
  const indice = getIndice()
  const limit = Math.min(Math.max(opciones.limit || 5, 1), 50)
  const filtros = opciones.filtros || null
  const alpha = opciones.alpha === undefined ? 0.5 : Number(opciones.alpha)
  const t0 = Date.now()

  const lexicos = puntajesBm25(indice, consulta)
  let vector = null
  if (semanticaDisponible()) {
    try {
      vector = await embeberConsulta(consulta)
    } catch (e) {
      console.warn(`[corpus] embeddings no disponibles: ${e.message}`)
    }
  }

  if (!vector) {
    return { resultados: mejores(indice, lexicos, limit, filtros), modo: 'keyword', alpha: null }
  }

  const densos = puntajesCoseno(indice, vector)
  if (!densos) {
    return { resultados: mejores(indice, lexicos, limit, filtros), modo: 'keyword', alpha: null }
  }

  const dl = normalizar(densos)
  const ll = normalizar(lexicos)
  const fusion = new Float64Array(indice.n)
  for (let i = 0; i < indice.n; i++) {
    fusion[i] = alpha * dl[i] + (1 - alpha) * ll[i]
  }

  return {
    resultados: mejores(indice, fusion, limit, filtros),
    modo: 'hibrida',
    alpha,
    ms_vector: Date.now() - t0,
  }
}

export function catalogoCorpus() {
  return catalogo(getIndice())
}

export function totalFragmentos() {
  return getDatos().n
}
