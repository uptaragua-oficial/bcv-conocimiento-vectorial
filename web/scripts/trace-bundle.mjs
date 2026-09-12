/**
 * Verifica qué archivos incluiría Vercel en el bundle de cada función.
 *
 * Cubre las dos configuraciones posibles en Vercel:
 *   - Root Directory = `web`      → entradas en `web/api/`
 *   - Root Directory = repositorio → entradas en `api/` (re-export)
 *
 * Riesgo que cubre: que `corpus.json` (3.7 MB) no se empaquete y la función
 * falle en producción con ENOENT.
 *
 * Uso:
 *   npm run trace
 */
import { stat } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { nodeFileTrace } from '@vercel/nft'

const AQUI = dirname(fileURLToPath(import.meta.url))
const WEB = join(AQUI, '..')
const REPO = join(WEB, '..')

const CONJUNTOS = [
  { nombre: 'Root Directory = web', base: WEB, entradas: ['api/chat.js', 'api/search.js', 'api/catalogo.js', 'api/health.js'] },
  { nombre: 'Root Directory = repo', base: REPO, entradas: ['api/chat.js', 'api/search.js', 'api/catalogo.js', 'api/health.js'] },
]

let fallos = 0

for (const { nombre, base, entradas } of CONJUNTOS) {
  const rutas = entradas.map((e) => join(base, e))
  if (!rutas.every((r) => existsSync(r))) {
    console.log(`\n[${nombre}] omitido (no existen las entradas)`)
    continue
  }

  const { fileList } = await nodeFileTrace(rutas, { base })
  const lista = [...fileList]
  const corpus = lista.filter((f) => f.endsWith('corpus.json'))
  const libs = lista.filter((f) => f.includes('_lib'))

  let bytes = 0
  for (const f of lista) {
    try {
      bytes += (await stat(join(base, f))).size
    } catch {
      /* archivo virtual */
    }
  }

  const ok = corpus.length > 0
  if (!ok) fallos++

  console.log(`\n[${nombre}]`)
  console.log(`  archivos trazados : ${lista.length}`)
  console.log(`  módulos _lib      : ${libs.length}`)
  console.log(`  corpus.json       : ${ok ? 'INCLUIDO ✔' : 'FALTANTE ✘'}`)
  console.log(`  tamaño del bundle : ${(bytes / 1e6).toFixed(2)} MB`)
}

if (fallos) {
  console.error('\nERROR: el corpus no se empaquetaría en alguna configuración. Revisa includeFiles en vercel.json.')
  process.exit(1)
}
console.log('\nOK: el bundle incluye el corpus en todas las configuraciones comprobadas.')
