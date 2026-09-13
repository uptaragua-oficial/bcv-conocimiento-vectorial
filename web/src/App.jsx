import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import Mensaje from './components/Mensaje.jsx'
import Filtros from './components/Filtros.jsx'
import Sugerencias from './components/Sugerencias.jsx'
import Configuracion from './components/Configuracion.jsx'

const DISCLAIMER =
  'Este asistente entrega información normativa de fuentes públicas del BCV y no presta asesoría legal ni financiera. Verifique siempre el texto oficial.'

export default function App() {
  const [mensajes, setMensajes] = useState([])
  const [entrada, setEntrada] = useState('')
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState(null)
  const [filtros, setFiltros] = useState({})
  const [catalogo, setCatalogo] = useState({
    tipos_norma: [],
    materias: [],
    generacion_llm: false,
    proveedor_llm: null,
  })
  const [estado, setEstado] = useState(null)
  const [configAbierto, setConfigAbierto] = useState(false)
  const finRef = useRef(null)

  useEffect(() => {
    api
      .catalogo()
      .then(setCatalogo)
      .catch(() => setCatalogo((c) => ({ ...c, offline: true })))
    api.health().then(setEstado).catch(() => setEstado({ status: 'offline' }))
  }, [])

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [mensajes, cargando])

  async function enviar(texto) {
    const consulta = (texto ?? entrada).trim()
    if (!consulta || cargando) return

    setError(null)
    setEntrada('')
    const historial = mensajes.map((m) => ({ rol: m.rol, contenido: m.contenido }))
    setMensajes((prev) => [...prev, { rol: 'user', contenido: consulta }])
    setCargando(true)

    try {
      const data = await api.chat({ mensaje: consulta, filtros: Object.keys(filtros).length ? filtros : null, historial })
      setMensajes((prev) => [
        ...prev,
        {
          rol: 'assistant',
          contenido: data.respuesta,
          citas: data.citas,
          meta: { modo: data.modo_generacion, ms: data.latencia_ms, n: data.n_fragmentos, modelo: data.modelo },
        },
      ])
    } catch (e) {
      setError(e.message || 'No fue posible consultar el servicio.')
      setMensajes((prev) => [
        ...prev,
        {
          rol: 'assistant',
          contenido:
            'No pude conectar con el servicio de consulta. Verifica que el backend esté disponible e inténtalo de nuevo.',
          error: true,
        },
      ])
    } finally {
      setCargando(false)
    }
  }

  function limpiar() {
    setMensajes([])
    setError(null)
  }

  return (
    <div className="flex h-full flex-col bg-[#eef3f9]">
      {/* Encabezado */}
      <header className="border-b border-bcv-navy/10 bg-gradient-to-r from-bcv-navy to-bcv-blue text-white shadow">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-lg font-bold leading-tight sm:text-xl">
              Consulta Normativa · Banco Central de Venezuela
            </h1>
            <p className="text-xs text-blue-100 sm:text-sm">
              Asistente conversacional sobre el corpus jurídico-normativo del BCV
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-1 ${
                estado?.status === 'ok' ? 'bg-emerald-500/20 text-emerald-100' : 'bg-red-500/20 text-red-100'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${estado?.status === 'ok' ? 'bg-emerald-300' : 'bg-red-300'}`} />
              {estado?.status === 'ok' ? 'Servicio activo' : 'Servicio no disponible'}
            </span>
            <span className="rounded-full bg-white/15 px-2 py-1">
              {catalogo.generacion_llm
                ? `LLM · ${catalogo.proveedor_llm || 'activo'}`
                : 'Modo extractivo'}
            </span>
            <span className="rounded-full bg-white/15 px-2 py-1">
              {catalogo.recuperacion === 'hibrida' ? 'Búsqueda híbrida' : 'Búsqueda BM25'}
            </span>
            {catalogo.rerank && (
              <span
                className="rounded-full bg-white/15 px-2 py-1"
                title={`Reordenación con cross-encoder${catalogo.modelo_rerank ? ` · ${catalogo.modelo_rerank}` : ''}`}
              >
                Rerank
              </span>
            )}
            <button
              onClick={() => setConfigAbierto((v) => !v)}
              title="Configurar la dirección del backend"
              className="rounded-full bg-white/15 px-2 py-1 hover:bg-white/25"
            >
              ⚙ Backend
            </button>
            {mensajes.length > 0 && (
              <button onClick={limpiar} className="rounded-full bg-white/15 px-2 py-1 hover:bg-white/25">
                Nueva consulta
              </button>
            )}
          </div>
        </div>
      </header>

      <Configuracion abierto={configAbierto} onCerrar={() => setConfigAbierto(false)} />

      {/* Conversación */}
      <main className="mx-auto w-full max-w-5xl flex-1 overflow-y-auto px-4 py-5">
        {estado && estado.status !== 'ok' && (
          <div className="mb-4 rounded-lg border-l-4 border-bcv-gold bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <p className="font-semibold">El servicio de consulta no está configurado o no responde.</p>
            <p className="mt-1 text-xs">
              Dirección actual: <code className="rounded bg-white px-1">{api.base}</code>
            </p>
            <button
              onClick={() => setConfigAbierto(true)}
              className="mt-2 rounded-lg bg-bcv-navy px-3 py-1.5 text-xs font-semibold text-white hover:bg-bcv-blue"
            >
              ⚙ Configurar la dirección del backend
            </button>
          </div>
        )}
        {mensajes.length === 0 ? (
          <Sugerencias onElegir={(t) => enviar(t)} />
        ) : (
          <div className="flex flex-col gap-4">
            {mensajes.map((m, i) => (
              <Mensaje key={i} mensaje={m} />
            ))}
            {cargando && (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <span className="h-2 w-2 animate-pulse rounded-full bg-bcv-blue" />
                Consultando el corpus normativo…
              </div>
            )}
          </div>
        )}
        <div ref={finRef} />
      </main>

      {/* Controles e entrada */}
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-5xl px-4 py-3">
          {error && (
            <div className="mb-2 rounded border-l-4 border-red-400 bg-red-50 px-3 py-2 text-xs text-red-800">
              {error}
            </div>
          )}
          <Filtros catalogo={catalogo} filtros={filtros} setFiltros={setFiltros} />
          <form
            className="mt-2 flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              enviar()
            }}
          >
            <textarea
              rows={1}
              value={entrada}
              onChange={(e) => setEntrada(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  enviar()
                }
              }}
              placeholder="Escriba su consulta normativa… (p. ej. ¿Qué requisitos exige el BCV a los operadores cambiarios?)"
              className="max-h-32 min-h-[42px] flex-1 resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-bcv-blue focus:ring-1 focus:ring-bcv-blue"
            />
            <button
              type="submit"
              disabled={cargando || !entrada.trim()}
              className="h-[42px] rounded-lg bg-bcv-navy px-4 text-sm font-semibold text-white transition hover:bg-bcv-blue disabled:cursor-not-allowed disabled:opacity-40"
            >
              Consultar
            </button>
          </form>
          <p className="mt-2 text-[11px] leading-snug text-slate-500">{DISCLAIMER}</p>
        </div>
      </footer>
    </div>
  )
}
