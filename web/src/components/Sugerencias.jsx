const PREGUNTAS = [
  '¿Qué requisitos exige el BCV para ser operador cambiario autorizado?',
  '¿Cómo se determina el tipo de cambio oficial en Venezuela?',
  '¿Qué establece el Convenio Cambiario sobre las mesas de cambio?',
  '¿Cuáles son las obligaciones de los sujetos obligados en materia cambiaria?',
  '¿Qué normativa regula el sistema de pagos y las transferencias?',
  '¿Qué dice la Ley del Banco Central de Venezuela sobre sus funciones?',
]

export default function Sugerencias({ onElegir }) {
  return (
    <div className="mx-auto max-w-3xl pt-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-base font-bold text-bcv-navy">
          Consultas normativas y legales del BCV
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Pregunte en lenguaje natural sobre leyes, resoluciones, convenios cambiarios, circulares y
          actos administrativos publicados por el Banco Central de Venezuela. Cada respuesta incluye
          las <strong className="font-semibold text-bcv-navy">fuentes oficiales</strong> de donde proviene.
        </p>

        <p className="mt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Pruebe con una de estas consultas
        </p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {PREGUNTAS.map((p) => (
            <button
              key={p}
              onClick={() => onElegir(p)}
              className="rounded-lg border border-slate-200 px-3 py-2 text-left text-xs text-slate-700 transition hover:border-bcv-blue hover:bg-bcv-soft hover:text-bcv-navy"
            >
              {p}
            </button>
          ))}
        </div>

        <div className="mt-4 rounded-lg border-l-4 border-bcv-gold bg-amber-50 px-3 py-2 text-[11px] text-amber-900">
          El asistente <strong>informa</strong> sobre el texto normativo; no presta asesoría legal ni
          financiera. Ante cualquier decisión, consulte siempre la fuente oficial.
        </div>
      </div>
    </div>
  )
}
