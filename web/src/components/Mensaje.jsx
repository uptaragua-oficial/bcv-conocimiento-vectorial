import Citas from './Citas.jsx'

/** Renderiza texto con **negritas**, saltos de línea y referencias [n]. */
function Texto({ contenido }) {
  const bloques = String(contenido || '').split('\n')
  return (
    <>
      {bloques.map((linea, i) => {
        if (!linea.trim()) return <div key={i} className="h-2" />
        const partes = linea.split(/(\*\*[^*]+\*\*|\[\d+\])/g).filter(Boolean)
        return (
          <p key={i} className="leading-relaxed">
            {partes.map((p, j) => {
              if (p.startsWith('**') && p.endsWith('**')) {
                return (
                  <strong key={j} className="font-semibold text-bcv-navy">
                    {p.slice(2, -2)}
                  </strong>
                )
              }
              if (/^\[\d+\]$/.test(p)) {
                return (
                  <span
                    key={j}
                    className="mx-0.5 inline-flex items-center rounded bg-bcv-soft px-1.5 text-[11px] font-semibold text-bcv-blue"
                  >
                    {p}
                  </span>
                )
              }
              return <span key={j}>{p}</span>
            })}
          </p>
        )
      })}
    </>
  )
}

export default function Mensaje({ mensaje }) {
  const esUsuario = mensaje.rol === 'user'
  if (esUsuario) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-bcv-navy px-4 py-2.5 text-sm text-white shadow-sm">
          {mensaje.contenido}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[92%]">
        <div
          className={`rounded-2xl rounded-bl-sm border px-4 py-3 text-sm shadow-sm ${
            mensaje.error ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-white'
          }`}
        >
          <Texto contenido={mensaje.contenido} />
          {mensaje.meta && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
              <span className="rounded bg-bcv-soft px-1.5 py-0.5 font-semibold text-bcv-blue">
                {mensaje.meta.modo === 'groq' ? `LLM${mensaje.meta.modelo ? ` · ${mensaje.meta.modelo}` : ''}` : 'Extractivo'}
              </span>
              <span>{mensaje.meta.n} fragmentos</span>
              <span>{Math.round(mensaje.meta.ms)} ms</span>
            </div>
          )}
        </div>
        {mensaje.citas?.length > 0 && <Citas citas={mensaje.citas} />}
      </div>
    </div>
  )
}
