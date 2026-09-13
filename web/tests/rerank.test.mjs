/**
 * Pruebas del rerank (cross-encoder por API).
 *
 * Se levanta un servidor local que imita el formato estándar (Jina, Cohere,
 * Voyage, TEI…) para comprobar que:
 *   * reordena según `relevance_score` y mapea bien el `index`;
 *   * completa los candidatos que el proveedor no devuelve;
 *   * recorta el texto enviado;
 *   * y, sobre todo, que **nunca** rompe la búsqueda si el proveedor falla.
 */
import assert from 'node:assert/strict'
import { test, before, after } from 'node:test'
import { createServer } from 'node:http'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '..')
const { reordenar, rerankConfig, rerankDisponible } = await import(
  join(RAIZ, 'api/_lib/rerank.js')
)

let servidor
let url
let ultimaPeticion
let modoRespuesta = 'ok'

before(async () => {
  servidor = createServer((req, res) => {
    let cuerpo = ''
    req.on('data', (c) => (cuerpo += c))
    req.on('end', () => {
      ultimaPeticion = JSON.parse(cuerpo)
      if (modoRespuesta === 'error') {
        res.writeHead(500, { 'Content-Type': 'application/json' })
        return res.end(JSON.stringify({ detail: 'boom' }))
      }
      if (modoRespuesta === 'basura') {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        return res.end('no es json')
      }
      if (modoRespuesta === 'vacio') {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        return res.end(JSON.stringify({ results: [] }))
      }
      // Relevancia = número de coincidencias de palabras de la consulta
      const palabras = ultimaPeticion.query.toLowerCase().split(/\s+/)
      const results = ultimaPeticion.documents
        .map((doc, index) => ({
          index,
          relevance_score: palabras.filter((p) => doc.toLowerCase().includes(p)).length,
        }))
        .sort((a, b) => b.relevance_score - a.relevance_score)
      const recortados = modoRespuesta === 'parcial' ? results.slice(0, 2) : results
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ results: recortados }))
    })
  })
  await new Promise((r) => servidor.listen(0, '127.0.0.1', r))
  url = `http://127.0.0.1:${servidor.address().port}/rerank`
})

after(() => {
  servidor.close()
  delete process.env.RERANK_API_URL
})

const ITEMS = [
  { doc_id: 'a', texto: 'Artículo sobre encaje legal de los bancos' },
  { doc_id: 'b', texto: 'operador cambiario autorizado para operar' },
  { doc_id: 'c', texto: 'tasas de interés y encaje' },
]

test('sin proveedor configurado el orden no se toca', async () => {
  delete process.env.RERANK_API_URL
  assert.equal(rerankConfig(), null)
  assert.equal(rerankDisponible(), false)
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.deepEqual(salida.map((i) => i.doc_id), ['a', 'b', 'c'])
})

test('RERANK_ACTIVO=false lo desactiva aunque haya proveedor', async () => {
  process.env.RERANK_API_URL = url
  process.env.RERANK_ACTIVO = 'false'
  assert.equal(rerankDisponible(), false)
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.deepEqual(salida.map((i) => i.doc_id), ['a', 'b', 'c'])
  delete process.env.RERANK_ACTIVO
})

test('reordena según relevance_score y anota rerank_score', async () => {
  process.env.RERANK_API_URL = url
  modoRespuesta = 'ok'
  assert.equal(rerankDisponible(), true)

  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.deepEqual(salida.map((i) => i.doc_id), ['b', 'a', 'c'])
  assert.equal(typeof salida[0].rerank_score, 'number')
  assert.ok(salida[0].rerank_score > salida[2].rerank_score)
})

test('envía el formato estándar con modelo, query, documents y top_n', async () => {
  process.env.RERANK_API_URL = url
  process.env.RERANK_MODEL = 'proveedor/reranker-x'
  await reordenar('encaje', ITEMS, { limit: 2 })
  assert.equal(ultimaPeticion.model, 'proveedor/reranker-x')
  assert.equal(ultimaPeticion.query, 'encaje')
  assert.equal(ultimaPeticion.top_n, 2)
  assert.equal(ultimaPeticion.documents.length, 3)
  delete process.env.RERANK_MODEL
})

test('recorta el texto enviado al proveedor', async () => {
  process.env.RERANK_API_URL = url
  const largo = [{ doc_id: 'x', texto: 'a'.repeat(9000) }]
  await reordenar('a', [...largo, { doc_id: 'y', texto: 'b' }], { limit: 2 })
  assert.equal(ultimaPeticion.documents[0].length, 2000)
})

test('completa los candidatos que el proveedor no devuelve', async () => {
  process.env.RERANK_API_URL = url
  modoRespuesta = 'parcial' // el proveedor solo devuelve 2 de 3
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.equal(salida.length, 3, 'no se pierden candidatos')
  assert.equal(salida[0].doc_id, 'b')
  assert.deepEqual([...salida.map((i) => i.doc_id)].sort(), ['a', 'b', 'c'])
  modoRespuesta = 'ok'
})

test('si el proveedor falla, se conserva el orden original', async () => {
  process.env.RERANK_API_URL = url
  for (const modo of ['error', 'basura', 'vacio']) {
    modoRespuesta = modo
    const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
    assert.deepEqual(
      salida.map((i) => i.doc_id),
      ['a', 'b', 'c'],
      `modo ${modo}: debe degradar sin romper`,
    )
  }
  modoRespuesta = 'ok'
})

test('si el proveedor no responde, se conserva el orden original', async () => {
  process.env.RERANK_API_URL = 'http://127.0.0.1:1/rerank'
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.deepEqual(salida.map((i) => i.doc_id), ['a', 'b', 'c'])
})

test('con menos de dos candidatos no se llama al proveedor', async () => {
  process.env.RERANK_API_URL = url
  ultimaPeticion = null
  const salida = await reordenar('x', [ITEMS[0]], { limit: 5 })
  assert.equal(ultimaPeticion, null)
  assert.deepEqual(salida.map((i) => i.doc_id), ['a'])
})

test('RERANK_CANDIDATOS se acota a un rango razonable', () => {
  process.env.RERANK_API_URL = url
  process.env.RERANK_CANDIDATOS = '5000'
  assert.equal(rerankConfig().candidatos, 100)
  process.env.RERANK_CANDIDATOS = '1'
  assert.equal(rerankConfig().candidatos, 10)
  delete process.env.RERANK_CANDIDATOS
})
