/**
 * Cliente del API del portal de consultas normativas.
 *
 * La URL del backend se resuelve en este orden (de mayor a menor prioridad):
 *   1. Ajuste guardado por el usuario en el navegador (localStorage).
 *   2. Parámetro de URL:  ?api=https://mi-backend
 *   3. Variable de compilación VITE_API_URL.
 *   4. Valor por defecto para desarrollo local.
 *
 * Así el portal puede apuntar a cualquier backend (Space, túnel, servidor
 * propio) sin necesidad de recompilar ni redesplegar en Vercel.
 */
const CLAVE = 'bcv.apiUrl'

function normalizar(url) {
  return (url || '').trim().replace(/\/+$/, '')
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
  return (
    desdeAlmacen() ||
    desdeParametro() ||
    normalizar(import.meta.env.VITE_API_URL) ||
    'http://localhost:8000'
  )
}

/** Fija (o limpia, con cadena vacía) la URL del backend y recarga. */
export function fijarBase(url) {
  const limpia = normalizar(url)
  try {
    if (limpia) localStorage.setItem(CLAVE, limpia)
    else localStorage.removeItem(CLAVE)
  } catch {
    /* almacenamiento no disponible */
  }
}

async function pedir(ruta, opciones = {}) {
  const base = obtenerBase()
  const resp = await fetch(`${base}${ruta}`, {
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
    return obtenerBase()
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
