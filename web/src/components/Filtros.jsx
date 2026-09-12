export default function Filtros({ catalogo, filtros, setFiltros }) {
  const cambiar = (clave) => (e) => {
    const valor = e.target.value
    setFiltros((prev) => {
      const nuevo = { ...prev }
      if (valor) nuevo[clave] = valor
      else delete nuevo[clave]
      return nuevo
    })
  }

  const hayFiltros = Object.keys(filtros).length > 0
  const selectCls =
    'rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs outline-none focus:border-bcv-blue'

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold text-slate-600">Filtrar por:</span>

      <select value={filtros.materia || ''} onChange={cambiar('materia')} className={selectCls}>
        <option value="">Todas las materias</option>
        {(catalogo.materias || []).map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>

      <select value={filtros.tipo_norma || ''} onChange={cambiar('tipo_norma')} className={selectCls}>
        <option value="">Todos los tipos</option>
        {(catalogo.tipos_norma || []).map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>

      {hayFiltros && (
        <button
          type="button"
          onClick={() => setFiltros({})}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          Limpiar filtros
        </button>
      )}
    </div>
  )
}
