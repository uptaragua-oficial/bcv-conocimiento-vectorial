/**
 * Emulador local de Vercel para el modo nativo.
 *
 * Sirve el frontend compilado (`dist/`) y enruta `/api/<nombre>` a las
 * funciones serverless de `api/<nombre>.js`, replicando el comportamiento
 * del despliegue real. Permite verificar todo sin subir nada.
 *
 * Uso:
 *   npm run build && npm run dev:vercel
 *   # abrir http://localhost:3000
 */
import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname } from 'node:path'

const AQUI = dirname(fileURLToPath(import.meta.url))
const WEB = join(AQUI, '..')
const REPO = join(WEB, '..')

// Modo raíz: replica un despliegue con Root Directory = repositorio
// (funciones en `api/` de la raíz, estáticos en `web/dist`).
const MODO_RAIZ = process.env.MODO_RAIZ === '1' || process.argv.includes('--raiz')
const DIST = join(WEB, 'dist')
const DIR_API = MODO_RAIZ ? join(REPO, 'api') : join(WEB, 'api')
const PUERTO = Number(process.env.PORT || (MODO_RAIZ ? 3001 : 3000))

const TIPOS = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
}

async function leerCuerpo(req) {
  const trozos = []
  for await (const t of req) trozos.push(t)
  if (!trozos.length) return {}
  try {
    return JSON.parse(Buffer.concat(trozos).toString('utf-8'))
  } catch {
    return {}
  }
}

function resVercel(res) {
  res.status = (c) => {
    res.statusCode = c
    return res
  }
  res.json = (o) => {
    if (!res.getHeader('Content-Type')) res.setHeader('Content-Type', 'application/json; charset=utf-8')
    res.end(JSON.stringify(o))
    return res
  }
  return res
}

const servidor = createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`)
  const ruta = url.pathname

  // --- Rutas API ---
  if (ruta.startsWith('/api/')) {
    const nombre = ruta.slice(5).replace(/\/+$/, '') || 'index'
    try {
      const modulo = await import(pathToFileURL(join(DIR_API, `${nombre}.js`)).href)
      const handler = modulo.default
      if (typeof handler !== 'function') throw new Error('sin export default')
      req.query = Object.fromEntries(url.searchParams.entries())
      req.body = req.method === 'POST' ? await leerCuerpo(req) : {}
      return handler(req, resVercel(res))
    } catch (e) {
      res.statusCode = 404
      res.setHeader('Content-Type', 'application/json; charset=utf-8')
      return res.end(JSON.stringify({ detail: `Función no encontrada: ${nombre} (${e.message})` }))
    }
  }

  // --- Estáticos ---
  const relativo = ruta === '/' ? '/index.html' : ruta
  const destino = join(DIST, normalize(relativo).replace(/^(\.\.[/\\])+/, ''))
  try {
    const info = await stat(destino)
    if (!info.isFile()) throw new Error('no es archivo')
    const contenido = await readFile(destino)
    res.statusCode = 200
    res.setHeader('Content-Type', TIPOS[extname(destino)] || 'application/octet-stream')
    return res.end(contenido)
  } catch {
    // Fallback SPA
    const index = await readFile(join(DIST, 'index.html'))
    res.statusCode = 200
    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    return res.end(index)
  }
})

servidor.listen(PUERTO, () => {
  console.log(`Emulador Vercel activo en http://localhost:${PUERTO}`)
  console.log(`  Modo:     ${MODO_RAIZ ? 'Root Directory = raíz del repositorio' : 'Root Directory = web'}`)
  console.log(`  Frontend: ${DIST}`)
  console.log(`  API:      ${DIR_API}`)
})
