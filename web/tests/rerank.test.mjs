/**
 * Pruebas del rerank (cross-encoder por API).
 *
 * Se levanta un servidor local que imita **los dos dialectos**:
 *   * `/rerank`             → formato estándar (Jina, Cohere, Voyage, TEI)
 *   * `/inference/{modelo}` → formato propio de DeepInfra
 *
 * Se comprueba que cada uno se construye y se interpreta bien, que se completan
 * los candidatos ausentes y que, sobre todo, la búsqueda **nunca** se rompe si
 * el proveedor falla.
 */
import assert from 'node:assert/strict'
import { test, before, after } from 'node:test'
import { createServer } from 'node:http'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '..')
const { reordenar, rerankConfig, rerankDisponible, detectarFormato } = await import(
  join(RAIZ, 'api/_lib/rerank.js')
)

let servidor
let base
let ultimaPeticion
let ultimaRuta
let modoRespuesta = 'ok'

/** Relevancia de mentira: nº de palabras de la consulta presentes en el documento. */
function relevancias(consulta, documentos) {
  const palabras = consulta.toLowerCase().split(/\s+/)
  return documentos.map((d) => palabras.filter((p) => d.toLowerCase().includes(p)).length)
}

before(async () => {
  servidor = createServer((req, res) => {
    let cuerpo = ''
    req.on('data', (c) => (cuerpo += c))
    req.on('end', () => {
      ultimaPeticion = JSON.parse(cuerpo)
      ultimaRuta = req.url
      const json = (o, code = 200) => {
        res.writeHead(code, { 'Content-Type': 'application/json' })
        res.end(typeof o === 'string' ? o : JSON.stringify(o))
      }

      if (modoRespuesta === 'error') return json({ detail: 'boom' }, 500)
      if (modoRespuesta === 'basura') return json('no es json')
      if (modoRespuesta === 'vacio') return json({ results: [], scores: [] })

      const esDeepInfra = req.url.includes('/inference/')

      if (esDeepInfra) {
        // `scores` va en el MISMO orden que los documentos, sin ordenar.
        const scores = relevancias(ultimaPeticion.queries[0], ultimaPeticion.documents)
        if (modoRespuesta === 'desalineado') scores.pop()
        return json({ scores, input_tokens: 348 })
      }

      const results = relevancias(ultimaPeticion.query, ultimaPeticion.documents)
        .map((s, index) => ({ index, relevance_score: s }))
        .sort((a, b) => b.relevance_score - a.relevance_score)
      return json({ results: modoRespuesta === 'parcial' ? results.slice(0, 2) : results })
    })
  })
  await new Promise((r) => servidor.listen(0, '127.0.0.1', r))
  base = `http://127.0.0.1:${servidor.address().port}`
})

after(() => {
  servidor.close()
  delete process.env.RERANK_API_URL
  delete process.env.RERANK_FORMATO
  delete process.env.RERANK_MODEL
  delete process.env.RERANK_INSTRUCTION
})

const ITEMS = [
  { doc_id: 'a', texto: 'Artículo sobre encaje legal de los bancos' },
  { doc_id: 'b', texto: 'operador cambiario autorizado para operar' },
  { doc_id: 'c', texto: 'tasas de interés y encaje' },
]

// ---------------- Detección de dialecto ----------------
test('el formato se deduce de la URL y se puede forzar', () => {
  assert.equal(detectarFormato('', 'https://api.deepinfra.com/v1/inference/X'), 'deepinfra')
  assert.equal(detectarFormato('', 'https://api.jina.ai/v1/rerank'), 'estandar')
  // El valor explícito gana sobre la URL
  assert.equal(detectarFormato('estandar', 'https://api.deepinfra.com/v1/inference'), 'estandar')
  assert.equal(detectarFormato('deepinfra', 'http://localhost:9999/rerank'), 'deepinfra')
})

// ---------------- Sin proveedor ----------------
test('sin proveedor configurado el orden no se toca', async () => {
  delete process.env.RERANK_API_URL
  assert.equal(rerankConfig(), null)
  assert.equal(rerankDisponible(), false)
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.deepEqual(salida.map((i) => i.doc_id), ['a', 'b', 'c'])
})

test('RERANK_ACTIVO=false lo desactiva aunque haya proveedor', async () => {
  process.env.RERANK_API_URL = `${base}/rerank`
  process.env.RERANK_ACTIVO = 'false'
  assert.equal(rerankDisponible(), false)
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.deepEqual(salida.map((i) => i.doc_id), ['a', 'b', 'c'])
  delete process.env.RERANK_ACTIVO
})

// ---------------- Formato estándar ----------------
test('estándar: reordena según relevance_score y anota rerank_score', async () => {
  process.env.RERANK_API_URL = `${base}/rerank`
  modoRespuesta = 'ok'
  assert.equal(rerankConfig().formato, 'estandar')

  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.deepEqual(salida.map((i) => i.doc_id), ['b', 'a', 'c'])
  assert.ok(salida[0].rerank_score > salida[2].rerank_score)
})

test('estándar: envía modelo, query, documents y top_n', async () => {
  process.env.RERANK_API_URL = `${base}/rerank`
  process.env.RERANK_MODEL = 'proveedor/reranker-x'
  await reordenar('encaje', ITEMS, { limit: 2 })
  assert.equal(ultimaPeticion.model, 'proveedor/reranker-x')
  assert.equal(ultimaPeticion.query, 'encaje')
  assert.equal(ultimaPeticion.top_n, 2)
  assert.equal(ultimaPeticion.documents.length, 3)
  assert.equal(ultimaPeticion.queries, undefined, 'no debe usar el dialecto de DeepInfra')
  delete process.env.RERANK_MODEL
})

test('estándar: completa los candidatos que el proveedor no devuelve', async () => {
  process.env.RERANK_API_URL = `${base}/rerank`
  modoRespuesta = 'parcial' // el proveedor solo devuelve 2 de 3
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.equal(salida.length, 3, 'no se pierden candidatos')
  assert.equal(salida[0].doc_id, 'b')
  assert.deepEqual([...salida.map((i) => i.doc_id)].sort(), ['a', 'b', 'c'])
  modoRespuesta = 'ok'
})

// ---------------- Formato DeepInfra ----------------
test('DeepInfra: usa queries/documents y el modelo va en la URL', async () => {
  process.env.RERANK_API_URL = `${base}/inference`
  process.env.RERANK_MODEL = 'Qwen/Qwen3-Reranker-8B'
  modoRespuesta = 'ok'
  const cfg = rerankConfig()
  assert.equal(cfg.formato, 'deepinfra')
  assert.equal(cfg.url, `${base}/inference/Qwen/Qwen3-Reranker-8B`)

  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.equal(ultimaRuta, '/inference/Qwen/Qwen3-Reranker-8B')
  assert.deepEqual(ultimaPeticion.queries, ['operador cambiario'])
  assert.equal(ultimaPeticion.documents.length, 3)
  assert.equal(ultimaPeticion.model, undefined, 'el modelo no va en el cuerpo')
  assert.equal(ultimaPeticion.top_n, undefined, 'DeepInfra no admite top_n')
  assert.deepEqual(salida.map((i) => i.doc_id), ['b', 'a', 'c'])
})

test('DeepInfra: respeta el modelo escrito en la propia URL', async () => {
  process.env.RERANK_API_URL = `${base}/inference/Qwen/Qwen3-Reranker-4B`
  delete process.env.RERANK_MODEL
  const cfg = rerankConfig()
  assert.equal(cfg.modelo, 'Qwen/Qwen3-Reranker-4B')
  assert.equal(cfg.url, `${base}/inference/Qwen/Qwen3-Reranker-4B`)
})

test('DeepInfra: admite el marcador {model} en la URL', async () => {
  process.env.RERANK_API_URL = `${base}/inference/{model}`
  process.env.RERANK_MODEL = 'Qwen/Qwen3-Reranker-0.6B'
  const cfg = rerankConfig()
  assert.equal(cfg.url, `${base}/inference/Qwen/Qwen3-Reranker-0.6B`)
  assert.equal(cfg.modelo, 'Qwen/Qwen3-Reranker-0.6B')
})

test('DeepInfra: el modelo por defecto es Qwen3-Reranker-0.6B', () => {
  process.env.RERANK_API_URL = `${base}/inference`
  delete process.env.RERANK_MODEL
  assert.equal(rerankConfig().modelo, 'Qwen/Qwen3-Reranker-0.6B')
})

test('DeepInfra: ordena unos scores que vienen sin ordenar', async () => {
  process.env.RERANK_API_URL = `${base}/inference`
  modoRespuesta = 'ok'
  // La relevancia cruda de 'b' es la mayor, pero llega en la posición 1
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 2 })
  assert.deepEqual(salida.map((i) => i.doc_id), ['b', 'a'])
  assert.equal(salida.length, 2, 'top_n se aplica en el cliente')
})

test('DeepInfra: envía la instrucción cuando está configurada', async () => {
  process.env.RERANK_API_URL = `${base}/inference`
  process.env.RERANK_INSTRUCTION =
    'Dada una consulta sobre normativa del BCV, recupera los artículos que la responden'
  await reordenar('encaje', ITEMS, { limit: 2 })
  assert.match(ultimaPeticion.instruction, /normativa del BCV/)
  delete process.env.RERANK_INSTRUCTION
})

test('DeepInfra: si los scores no cuadran con los documentos, no se toca el orden', async () => {
  process.env.RERANK_API_URL = `${base}/inference`
  modoRespuesta = 'desalineado'
  const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
  assert.deepEqual(
    salida.map((i) => i.doc_id),
    ['a', 'b', 'c'],
    'un desalineamiento daría puntajes a los documentos equivocados',
  )
  modoRespuesta = 'ok'
})

// ---------------- Recorte y degradación ----------------
test('recorta el texto enviado al proveedor', async () => {
  process.env.RERANK_API_URL = `${base}/rerank`
  const largo = [{ doc_id: 'x', texto: 'a'.repeat(9000) }]
  await reordenar('a', [...largo, { doc_id: 'y', texto: 'b' }], { limit: 2 })
  assert.equal(ultimaPeticion.documents[0].length, 2000)
})

test('si el proveedor falla, se conserva el orden original', async () => {
  for (const [url, etiqueta] of [
    [`${base}/rerank`, 'estándar'],
    [`${base}/inference`, 'deepinfra'],
  ]) {
    process.env.RERANK_API_URL = url
    for (const modo of ['error', 'basura', 'vacio']) {
      modoRespuesta = modo
      const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
      assert.deepEqual(
        salida.map((i) => i.doc_id),
        ['a', 'b', 'c'],
        `${etiqueta} · modo ${modo}: debe degradar sin romper`,
      )
    }
  }
  modoRespuesta = 'ok'
})

test('si el proveedor no responde, se conserva el orden original', async () => {
  for (const url of ['http://127.0.0.1:1/rerank', 'http://127.0.0.1:1/inference']) {
    process.env.RERANK_API_URL = url
    const salida = await reordenar('operador cambiario', ITEMS, { limit: 3 })
    assert.deepEqual(salida.map((i) => i.doc_id), ['a', 'b', 'c'])
  }
})

test('con menos de dos candidatos no se llama al proveedor', async () => {
  process.env.RERANK_API_URL = `${base}/rerank`
  ultimaPeticion = null
  const salida = await reordenar('x', [ITEMS[0]], { limit: 5 })
  assert.equal(ultimaPeticion, null)
  assert.deepEqual(salida.map((i) => i.doc_id), ['a'])
})

test('RERANK_CANDIDATOS se acota a un rango razonable', () => {
  process.env.RERANK_API_URL = `${base}/rerank`
  process.env.RERANK_CANDIDATOS = '5000'
  assert.equal(rerankConfig().candidatos, 100)
  process.env.RERANK_CANDIDATOS = '1'
  assert.equal(rerankConfig().candidatos, 10)
  delete process.env.RERANK_CANDIDATOS
})
