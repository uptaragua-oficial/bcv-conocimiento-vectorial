/** GET /api/catalogo — valores disponibles para los filtros. */
import { catalogoCorpus, totalFragmentos } from './_lib/corpus.js'
import { proveedorLLM } from './_lib/rag.js'
import { preflight } from './_lib/http.js'

export default function handler(req, res) {
  if (preflight(req, res)) return

  const proveedor = proveedorLLM()
  return res.status(200).json({
    ...catalogoCorpus(),
    generacion_llm: Boolean(proveedor),
    proveedor_llm: proveedor ? proveedor.nombre : null,
    modelo_llm: proveedor ? proveedor.modelo : null,
    total_fragmentos: totalFragmentos(),
  })
}
