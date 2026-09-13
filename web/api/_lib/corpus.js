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
import { reordenar, rerankConfig, rerankDisponible } from './rerank.js'

const AQUI = dirname(fileURLToPath(import.meta.url))
const RUTA_CORPUS = join(AQUI, '..', '_data', 'corpus.json')

/**
 * Peso de la componente semántica en la fusión híbrida (`alpha`).
 *
 * **No es 0.5 por una razón medida.** Con α=0.5, el Art. 12 del Convenio
 * Cambiario N.º 1 no entraba ni siquiera entre los 20 primeros candidatos para
 * «¿Qué requisitos exige el BCV para ser operador cambiario autorizado?»; un
 * cross-encoder solo puede reordenar lo que recibe, así que no había forma de
 * rescatarlo. Con α=0.7 el artículo entra y el rerank lo deja 3.º.
 *
 * Coste medido en el conjunto de evaluación (150 consultas): 0.884 → 0.882 de
 * nDCG@5, dentro del error de muestreo. Ver `docs/RERANK.md`.
 */
export const ALPHA_POR_DEFECTO = 0.7

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
 *
 * Con `rerank: true` se recuperan primero `RERANK_CANDIDATOS` candidatos (30 por
 * defecto) y un cross-encoder externo los reordena por relevancia real. Es
 * justo lo que la fusión no puede hacer: un fragmento que repite el término de
 * la consulta muchas veces pero no responde a la pregunta puntúa alto en BM25 y
 * el cross-encoder lo baja.
 */
export async function buscarHibrido(consulta, opciones = {}) {
  const indice = getIndice()
  const limit = Math.min(Math.max(opciones.limit || 5, 1), 50)
  const filtros = opciones.filtros || null
  const alpha = opciones.alpha === undefined ? ALPHA_POR_DEFECTO : Number(opciones.alpha)
  // `rerank: undefined` = automático: se aplica si hay proveedor configurado.
  // `rerank: false` lo desactiva aunque lo haya.
  const quiereRerank =
    (opciones.rerank === true || opciones.rerank === undefined) && rerankDisponible()
  const nCandidatos = quiereRerank ? Math.max(rerankConfig().candidatos, limit) : limit
  const t0 = Date.now()

  const lexicos = puntajesBm25(indice, consulta)
  let vector = null
  if (semanticaDisponible() && vectoresAlineados()) {
    try {
      vector = await embeberConsulta(consulta)
    } catch (e) {
      console.warn(`[corpus] embeddings no disponibles: ${e.message}`)
    }
  }

  const terminar = async (candidatos, modo, alphaDevolvido) => {
    if (!quiereRerank || candidatos.length < 2) {
      return { resultados: candidatos.slice(0, limit), modo, alpha: alphaDevolvido, rerank: false }
    }
    const t1 = Date.now()
    const reordenados = await reordenar(consulta, candidatos, { limit })
    // `null` = se intentó y no se pudo (proveedor caído, clave inválida, respuesta
    // inservible). Se conserva el orden de la búsqueda y se informa con
    // honestidad: marcar `rerank: true` habiendo fallado oculta el problema.
    if (!reordenados) {
      return { resultados: candidatos.slice(0, limit), modo, alpha: alphaDevolvido, rerank: false }
    }
    return {
      resultados: reordenados,
      modo,
      alpha: alphaDevolvido,
      rerank: true,
      ms_rerank: Date.now() - t1,
    }
  }

  if (!vector) {
    return terminar(mejores(indice, lexicos, nCandidatos, filtros), 'keyword', null)
  }

  const densos = puntajesCoseno(indice, vector)
  if (!densos) {
    return terminar(mejores(indice, lexicos, nCandidatos, filtros), 'keyword', null)
  }

  const dl = normalizar(densos)
  const ll = normalizar(lexicos)
  const fusion = new Float64Array(indice.n)
  for (let i = 0; i < indice.n; i++) {
    fusion[i] = alpha * dl[i] + (1 - alpha) * ll[i]
  }

  const resultado = await terminar(mejores(indice, fusion, nCandidatos, filtros), 'hibrida', alpha)
  return { ...resultado, ms_vector: Date.now() - t0 }
}

/**
 * ¿Los vectores corresponden al corpus actual?
 *
 * Si el corpus crece (nuevas normas) y no se re-vectoriza, la matriz quedaría
 * más corta que el índice y la similitud coseno leería fuera de rango,
 * asignando 0 a los fragmentos nuevos. Es mejor detectarlo y usar BM25.
 */
export function vectoresAlineados() {
  const v = vectoresCorpus()
  if (!v) return false
  const alineados = v.n === getIndice().n
  if (!alineados) {
    console.warn(
      `[corpus] vectores desalineados: ${v.n} vectores para ${getIndice().n} fragmentos. ` +
        `Re-vectoriza el corpus; mientras tanto se usa solo BM25.`,
    )
  }
  return alineados
}

export function catalogoCorpus() {
  return catalogo(getIndice())
}

export function totalFragmentos() {
  return getDatos().n
}
