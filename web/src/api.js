/**
 * Cliente del API del Observatorio (backend en HuggingFace Space o local).
 *
 * La URL del backend se configura con VITE_API_URL:
 *   - Local:  VITE_API_URL=http://localhost:8000
 *   - Vercel: VITE_API_URL=https://<usuario>-<space>.hf.space
 */
const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function pedir(ruta, opciones = {}) {
  const resp = await fetch(`${API_URL}${ruta}`, {
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
  base: API_URL,
  health: () => pedir('/health'),
  stats: () => pedir('/stats'),
  catalogo: () => pedir('/catalogo'),
  chat: ({ mensaje, filtros, limit = 5, historial }) =>
    pedir('/chat', {
      method: 'POST',
      body: JSON.stringify({ mensaje, modo: 'hybrid', limit, filtros, historial }),
    }),
}
