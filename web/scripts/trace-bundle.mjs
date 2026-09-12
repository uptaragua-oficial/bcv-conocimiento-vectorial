/**
 * Verifica qué archivos incluiría Vercel en el bundle de cada función.
 *
 * Riesgo que cubre: que `api/_data/corpus.json` (3.7 MB) no se empaquete y la
 * función falle en producción con ENOENT. Se ejecuta antes de desplegar.
 *
 * Uso:
 *   npm run trace
 */
import { stat } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { nodeFileTrace } from '@vercel/nft'

const AQUI = dirname(fileURLToPath(import.meta.url))
const RAIZ = join(AQUI, '..')

const ENTRADAS = ['api/chat.js', 'api/search.js', 'api/catalogo.js', 'api/health.js']

const entradas = ENTRADAS.map((f) => join(RAIZ, f))
const { fileList, warnings } = await nodeFileTrace(entradas, { base: RAIZ })
const lista = [...fileList]

const corpus = lista.filter((f) => f.endsWith('corpus.json'))
const libs = lista.filter((f) => f.includes('api/_lib'))

let bytes = 0
for (const f of lista) {
  try {
    bytes += (await stat(join(RAIZ, f))).size
  } catch {
    /* archivo virtual */
  }
}

console.log(`Funciones analizadas: ${ENTRADAS.length}`)
console.log(`Archivos trazados:    ${lista.length}`)
console.log(`Módulos _lib:         ${libs.length}`)
console.log(`corpus.json:          ${corpus.length ? 'INCLUIDO ✔' : 'FALTANTE ✘'}`)
console.log(`Tamaño del bundle:    ${(bytes / 1e6).toFixed(2)} MB`)

if (warnings.length) {
  console.log(`Avisos: ${warnings.length}`)
  warnings.slice(0, 5).forEach((w) => console.log('  -', w.message || w))
}

if (!corpus.length) {
  console.error('\nERROR: el corpus no se empaquetaría. Revisa includeFiles en vercel.json.')
  process.exit(1)
}
console.log('\nOK: el bundle incluye el corpus y las librerías compartidas.')
