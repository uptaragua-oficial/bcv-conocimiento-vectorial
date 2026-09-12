/**
 * Pruebas de las funciones serverless del modo nativo de Vercel.
 * Se ejecutan con:  npm test   (node --test)
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '..')

const health = (await import(join(RAIZ, 'api/health.js'))).default
const catalogo = (await import(join(RAIZ, 'api/catalogo.js'))).default
const search = (await import(join(RAIZ, 'api/search.js'))).default
const chat = (await import(join(RAIZ, 'api/chat.js'))).default
const { tokenizar } = await import(join(RAIZ, 'api/_lib/bm25.js'))

/** Doble de `res` de Vercel. */
function mockRes() {
  const r = { statusCode: 200, headers: {}, body: null }
  r.setHeader = (k, v) => {
    r.headers[k.toLowerCase()] = v
  }
  r.status = (c) => {
    r.statusCode = c
    return r
  }
  r.json = (o) => {
    r.body = o
    return r
  }
  r.end = () => r
  return r
}

const peticion = (extra = {}) => ({ method: 'GET', query: {}, body: {}, ...extra })

// ---------------- Tokenizador ----------------
test('tokenizar normaliza acentos y descarta ruido', () => {
  const t = tokenizar('El Artículo 6° sobre la INFLACIÓN y los Bs.')
  assert.ok(t.includes('articulo'))
  assert.ok(t.includes('inflacion'))
  assert.ok(t.includes('sobre'))
  assert.ok(!t.includes('°'))
  // Se descartan tokens de un solo carácter
  assert.deepEqual(tokenizar('a b c'), [])
})

// ---------------- Endpoints ----------------
test('GET /api/health responde ok con el modo nativo', () => {
  const res = mockRes()
  health(peticion(), res)
  assert.equal(res.statusCode, 200)
  assert.equal(res.body.status, 'ok')
  assert.equal(res.body.motor, 'bm25')
  assert.ok(res.body.objetos > 1000)
})

test('GET /api/catalogo devuelve materias y tipos', () => {
  const res = mockRes()
  catalogo(peticion(), res)
  assert.equal(res.statusCode, 200)
  assert.ok(res.body.materias.length > 0)
  assert.ok(res.body.tipos_norma.length > 0)
  assert.equal(typeof res.body.generacion_llm, 'boolean')
})

test('OPTIONS responde preflight con CORS', () => {
  const res = mockRes()
  health(peticion({ method: 'OPTIONS' }), res)
  assert.equal(res.statusCode, 204)
  assert.equal(res.headers['access-control-allow-origin'], '*')
})

test('POST /api/search recupera y respeta filtros', () => {
  const res = mockRes()
  search(peticion({ method: 'POST', body: { query: 'operadores cambiarios', limit: 3 } }), res)
  assert.equal(res.statusCode, 200)
  assert.equal(res.body.n, 3)
  assert.ok(res.body.resultados[0].score > 0)
  assert.ok(res.body.resultados[0].fuente_url)

  const conFiltro = mockRes()
  search(
    peticion({ method: 'POST', body: { query: 'encaje', limit: 5, filtros: { materia: 'Encaje legal' } } }),
    conFiltro,
  )
  assert.equal(conFiltro.statusCode, 200)
  for (const r of conFiltro.body.resultados) {
    assert.equal(r.materia, 'Encaje legal')
  }
})

test('POST /api/search exige query', () => {
  const res = mockRes()
  search(peticion({ method: 'POST', body: {} }), res)
  assert.equal(res.statusCode, 422)
})

test('POST /api/chat devuelve respuesta citada', async () => {
  const res = mockRes()
  await chat(
    peticion({ method: 'POST', body: { mensaje: '¿Qué requisitos exige el BCV a los operadores cambiarios?', limit: 3 } }),
    res,
  )
  assert.equal(res.statusCode, 200)
  assert.equal(res.body.citas.length, 3)
  assert.ok(res.body.respuesta.length > 50)
  assert.ok(res.body.disclaimer.includes('no presta asesoría'))
  assert.ok(['groq', 'extractivo'].includes(res.body.modo_generacion))
})

test('POST /api/chat valida el mensaje mínimo', async () => {
  const res = mockRes()
  await chat(peticion({ method: 'POST', body: { mensaje: 'x' } }), res)
  assert.equal(res.statusCode, 422)
})

test('POST /api/chat rechaza métodos no permitidos', async () => {
  const res = mockRes()
  await chat(peticion({ method: 'DELETE', body: { mensaje: 'consulta válida' } }), res)
  assert.equal(res.statusCode, 405)
})
