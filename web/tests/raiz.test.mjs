/**
 * Pruebas de los re-exports de la raíz (`api/*.js`, CommonJS + import dinámico),
 * que se usan cuando en Vercel el Root Directory es la raíz del repositorio en
 * lugar de `web/`.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..')
const REPO = join(WEB, '..')
const require = createRequire(import.meta.url)

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

test('los re-exports de la raíz existen y son CommonJS', () => {
  for (const n of ['health', 'catalogo', 'search', 'chat']) {
    const ruta = join(REPO, 'api', `${n}.js`)
    assert.ok(existsSync(ruta), `falta api/${n}.js`)
    assert.equal(typeof require(ruta), 'function', `api/${n}.js no exporta una función`)
  }
})

test('GET /api/health desde la raíz delega en el handler real', async () => {
  const handler = require(join(REPO, 'api', 'health.js'))
  const res = mockRes()
  await handler(peticion(), res)
  assert.equal(res.statusCode, 200)
  assert.equal(res.body.status, 'ok')
  assert.ok(res.body.objetos > 1000)
})

test('POST /api/chat desde la raíz devuelve respuesta citada', async () => {
  const handler = require(join(REPO, 'api', 'chat.js'))
  const res = mockRes()
  await handler(
    peticion({ method: 'POST', body: { mensaje: '¿Qué son las mesas de cambio?', limit: 2 } }),
    res,
  )
  assert.equal(res.statusCode, 200)
  assert.equal(res.body.citas.length, 2)
  assert.ok(res.body.respuesta.length > 40)
})

test('POST /api/search desde la raíz respeta el límite', async () => {
  const handler = require(join(REPO, 'api', 'search.js'))
  const res = mockRes()
  await handler(peticion({ method: 'POST', body: { query: 'encaje legal', limit: 2 } }), res)
  assert.equal(res.statusCode, 200)
  assert.ok(res.body.n <= 2)
})
