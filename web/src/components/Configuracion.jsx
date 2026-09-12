import { useState } from 'react'
import { api, fijarBase } from '../api.js'

/**
 * Permite apuntar el portal a otro backend sin recompilar:
 * Space de HuggingFace, túnel de prueba o servidor propio.
 */
export default function Configuracion({ abierto, onCerrar }) {
  const [valor, setValor] = useState(api.base)

  if (!abierto) return null

  function guardar(e) {
    e.preventDefault()
    fijarBase(valor)
    window.location.reload()
  }

  function restablecer() {
    fijarBase('')
    window.location.reload()
  }

  return (
    <div className="border-b border-slate-200 bg-amber-50">
      <form onSubmit={guardar} className="mx-auto flex max-w-5xl flex-wrap items-end gap-2 px-4 py-3">
        <label className="flex-1 text-xs">
          <span className="mb-1 block font-semibold text-slate-700">
            Dirección del backend (API de consulta)
          </span>
          <input
            type="url"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            placeholder="https://mi-backend.ejemplo.com"
            className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-bcv-blue"
          />
        </label>
        <button
          type="submit"
          className="h-[34px] rounded-lg bg-bcv-navy px-3 text-xs font-semibold text-white hover:bg-bcv-blue"
        >
          Guardar y recargar
        </button>
        <button
          type="button"
          onClick={restablecer}
          className="h-[34px] rounded-lg border border-slate-300 bg-white px-3 text-xs text-slate-600 hover:bg-slate-50"
        >
          Restablecer
        </button>
        <button
          type="button"
          onClick={onCerrar}
          className="h-[34px] rounded-lg px-2 text-xs text-slate-500 hover:text-slate-800"
        >
          Cerrar
        </button>
        <p className="w-full text-[11px] text-amber-900">
          El valor se guarda solo en este navegador. También puede fijarse con{' '}
          <code className="rounded bg-white px-1">?api=https://…</code> en la dirección.
        </p>
      </form>
    </div>
  )
}
