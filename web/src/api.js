/**
 * Cliente del API del portal de consultas normativas.
 *
 * Resuelve la URL del backend en este orden:
 *   1. Ajuste guardado por el usuario (localStorage).
 *   2. Parámetro de URL:  ?api=https://mi-backend
 *   3. Variable de compilación VITE_API_URL.
 *   4. Modo automático:
 *        - en local  → backend Python en http://localhost:8000
 *        - desplegado → funciones serverless del propio Vercel (/api/*)
 *
 * Así el portal funciona en Vercel sin ningún servidor aparte, y puede
 * apuntarse a un backend externo (Space, túnel, servidor propio) sin recompilar.
 */
const CLAVE = 'bcv.apiUrl'

function normalizar(url) {
  return (url || '').trim().replace(/\/+$/, '')
}

function porDefecto() {
  const host = typeof window !== 'undefined' ? window.location.hostname : ''
  if (host === 'localhost' || host === '127.0.0.1' || host === '') return 'http://localhost:8000'
  return '' // rutas relativas: /api/* (modo nativo de Vercel)
}

function desdeParametro() {
  try {
    return normalizar(new URLSearchParams(window.location.search).get('api') || '')
  } catch {
    return ''
  }
}

function desdeAlmacen() {
  try {
    return normalizar(localStorage.getItem(CLAVE) || '')
  } catch {
    return ''
  }
}

export function obtenerBase() {
  const guardado = desdeAlmacen()
  if (guardado) return guardado
  const param = desdeParametro()
  if (param) return param
  const compilado = normalizar(import.meta.env.VITE_API_URL)
  if (compilado) return compilado
  return porDefecto()
}

/** Fija (o limpia, con cadena vacía) la URL del backend. */
export function fijarBase(url) {
  const limpia = normalizar(url)
  try {
    if (limpia) localStorage.setItem(CLAVE, limpia)
    else localStorage.removeItem(CLAVE)
  } catch {
    /* almacenamiento no disponible */
  }
}

/** En modo nativo las rutas viven bajo /api. */
function ruta(p) {
  return obtenerBase() ? p : `/api${p}`
}

/** Texto legible para la interfaz. */
export function descripcionBase() {
  const base = obtenerBase()
  return base || `${window.location.origin}/api (modo Vercel)`
}

async function pedir(camino, opciones = {}) {
  const url = `${obtenerBase()}${ruta(camino)}`
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opciones,
  })
  if (!resp.ok) {
    let detalle = `Error ${resp.status}`
    try {
      const j = await resp.json()
      detalle = j.detail || detalle
    } catch {
      /* respuesta no JSON */
    }
    throw new Error(detalle)
  }
  return resp.json()
}

export const api = {
  get base() {
    return descripcionBase()
  },
  health: () => pedir('/health'),
  stats: () => pedir('/stats'),
  catalogo: () => pedir('/catalogo'),
  chat: ({ mensaje, filtros, limit = 5, historial }) =>
    pedir('/chat', {
      method: 'POST',
      body: JSON.stringify({ mensaje, modo: 'hybrid', limit, filtros, historial }),
    }),
}
