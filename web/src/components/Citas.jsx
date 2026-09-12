const ETIQUETA_TIPO = {
  Resolución: 'Resolución',
  'Convenio cambiario': 'Convenio cambiario',
  Circular: 'Circular',
  'Aviso oficial': 'Aviso oficial',
  Ley: 'Ley',
  Decreto: 'Decreto',
  'Acto administrativo': 'Acto administrativo',
}

export default function Citas({ citas }) {
  return (
    <div className="mt-2">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Fuentes normativas ({citas.length})
      </p>
      <div className="flex flex-col gap-1.5">
        {citas.map((c) => (
          <details
            key={c.n}
            className="group rounded-lg border border-slate-200 bg-white/80 px-3 py-2 text-xs open:bg-white"
          >
            <summary className="flex cursor-pointer list-none items-center gap-2">
              <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-bcv-navy text-[11px] font-bold text-white">
                {c.n}
              </span>
              <span className="font-semibold text-bcv-navy">
                {ETIQUETA_TIPO[c.tipo_norma] || c.tipo_norma || 'Norma'}
              </span>
              {c.seccion && <span className="text-slate-600">· {c.seccion}</span>}
              {c.materia && (
                <span className="ml-auto shrink-0 rounded bg-bcv-soft px-1.5 py-0.5 text-[10px] font-medium text-bcv-blue">
                  {c.materia}
                </span>
              )}
            </summary>
            <div className="mt-2 border-t border-slate-100 pt-2">
              <p className="whitespace-pre-line text-slate-700">{c.fragmento}…</p>
              {c.fuente_url && (
                <a
                  href={c.fuente_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1.5 inline-block font-medium text-bcv-blue underline hover:text-bcv-navy"
                >
                  Ver documento oficial en bcv.org.ve ↗
                </a>
              )}
            </div>
          </details>
        ))}
      </div>
    </div>
  )
}
