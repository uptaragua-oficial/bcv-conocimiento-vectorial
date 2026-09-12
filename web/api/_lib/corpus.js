/**
 * Carga perezosa del corpus y del índice BM25 (modo nativo de Vercel).
 * El índice se construye una sola vez por instancia de función.
 *
 * El corpus se lee con `fs` para que Vercel lo incluya en el bundle de la
 * función (ver `includeFiles` en vercel.json), sin depender de import
 * attributes de JSON.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { construir, buscar, catalogo } from './bm25.js'

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

export function catalogoCorpus() {
  return catalogo(getIndice())
}

export function totalFragmentos() {
  return getDatos().n
}
