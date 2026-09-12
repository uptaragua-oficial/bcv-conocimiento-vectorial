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

test('POST /api/search recupera y respeta filtros', async () => {
  const res = mockRes()
  await search(peticion({ method: 'POST', body: { query: 'operadores cambiarios', limit: 3 } }), res)
  assert.equal(res.statusCode, 200)
  assert.equal(res.body.n, 3)
  assert.ok(res.body.resultados[0].score > 0)
  assert.ok(res.body.resultados[0].fuente_url)
  assert.ok(['keyword', 'hibrida'].includes(res.body.modo))

  const conFiltro = mockRes()
  await search(
    peticion({ method: 'POST', body: { query: 'encaje', limit: 5, filtros: { materia: 'Encaje legal' } } }),
    conFiltro,
  )
  assert.equal(conFiltro.statusCode, 200)
  for (const r of conFiltro.body.resultados) {
    assert.equal(r.materia, 'Encaje legal')
  }
})

test('POST /api/search exige query', async () => {
  const res = mockRes()
  await search(peticion({ method: 'POST', body: {} }), res)
  assert.equal(res.statusCode, 422)
})

test('el modo de recuperación coincide con la disponibilidad de embeddings', async () => {
  const { semanticaDisponible } = await import(join(RAIZ, 'api/_lib/embeddings.js'))
  const res = mockRes()
  await search(peticion({ method: 'POST', body: { query: 'mesas de cambio', limit: 2 } }), res)
  assert.equal(res.body.modo, semanticaDisponible() ? 'hibrida' : 'keyword')
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

// ---------------- Selección de proveedor de LLM ----------------
test('proveedorLLM prioriza DeepSeek y cae a Groq', async () => {
  const { proveedorLLM } = await import(join(RAIZ, 'api/_lib/rag.js'))
  const previo = {
    deepseek: process.env.DEEPSEEK_API_KEY,
    groq: process.env.GROQ_API_KEY,
    modelo: process.env.DEEPSEEK_MODEL,
    thinking: process.env.DEEPSEEK_THINKING,
  }
  try {
    delete process.env.DEEPSEEK_API_KEY
    delete process.env.GROQ_API_KEY
    delete process.env.DEEPSEEK_MODEL
    delete process.env.DEEPSEEK_THINKING
    assert.equal(proveedorLLM(), null)

    process.env.GROQ_API_KEY = 'gsk_prueba'
    assert.equal(proveedorLLM().nombre, 'groq')

    process.env.DEEPSEEK_API_KEY = 'sk-prueba'
    const p = proveedorLLM()
    assert.equal(p.nombre, 'deepseek')
    assert.equal(p.modelo, 'deepseek-flash')
    assert.equal(p.thinking, 'disabled')
    assert.ok(p.url.startsWith('https://api.deepseek.com'))

    process.env.DEEPSEEK_MODEL = 'deepseek-v4-pro'
    assert.equal(proveedorLLM().modelo, 'deepseek-v4-pro')

    process.env.DEEPSEEK_THINKING = 'enabled'
    assert.equal(proveedorLLM().thinking, 'enabled')
  } finally {
    for (const [k, v] of [
      ['DEEPSEEK_API_KEY', previo.deepseek],
      ['GROQ_API_KEY', previo.groq],
      ['DEEPSEEK_MODEL', previo.modelo],
      ['DEEPSEEK_THINKING', previo.thinking],
    ]) {
      if (v === undefined) delete process.env[k]
      else process.env[k] = v
    }
  }
})

// ---------------- Embeddings (búsqueda semántica) ----------------
test('embeddingsConfig usa OpenAI por defecto y admite otros proveedores', async () => {
  const { embeddingsConfig } = await import(join(RAIZ, 'api/_lib/embeddings.js'))
  const claves = ['EMBEDDINGS_API_KEY', 'OPENAI_API_KEY', 'EMBEDDINGS_MODEL', 'EMBEDDINGS_BASE_URL']
  const previo = Object.fromEntries(claves.map((k) => [k, process.env[k]]))
  try {
    claves.forEach((k) => delete process.env[k])
    assert.equal(embeddingsConfig(), null, 'sin clave no hay embeddings')

    process.env.OPENAI_API_KEY = 'sk-prueba'
    let cfg = embeddingsConfig()
    assert.equal(cfg.modelo, 'text-embedding-3-small')
    assert.ok(cfg.url.startsWith('https://api.openai.com/v1'))

    process.env.EMBEDDINGS_MODEL = 'BAAI/bge-m3'
    process.env.EMBEDDINGS_BASE_URL = 'https://api.deepinfra.com/v1/openai'
    cfg = embeddingsConfig()
    assert.equal(cfg.modelo, 'BAAI/bge-m3')
    assert.ok(cfg.url.startsWith('https://api.deepinfra.com/v1/openai'))
    assert.ok(cfg.url.endsWith('/embeddings'))
  } finally {
    for (const [k, v] of Object.entries(previo)) {
      if (v === undefined) delete process.env[k]
      else process.env[k] = v
    }
  }
})

test('normalizarL2 deja el vector con norma unitaria', async () => {
  const { normalizarL2 } = await import(join(RAIZ, 'api/_lib/embeddings.js'))
  const v = normalizarL2(Float32Array.from([3, 4]))
  assert.ok(Math.abs(Math.hypot(...v) - 1) < 1e-6)
  assert.ok(Math.abs(v[0] - 0.6) < 1e-6)
  assert.ok(Math.abs(v[1] - 0.8) < 1e-6)
})

test('sin vectores del corpus, la búsqueda cae a BM25', async () => {
  const { vectoresCorpus, metaVectores } = await import(join(RAIZ, 'api/_lib/embeddings.js'))
  // En el repositorio no se versionan vectores hasta vectorizar el corpus.
  if (metaVectores()) {
    assert.ok(vectoresCorpus(), 'si hay meta debe haber vectores')
  } else {
    assert.equal(vectoresCorpus(), null)
  }
})
