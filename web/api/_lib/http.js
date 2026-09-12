/** Utilidades HTTP compartidas por las funciones serverless. */

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
}

/** Devuelve `true` si ya respondió al preflight. */
function preflight(req, res) {
  cors(res);
  if (req.method === 'OPTIONS') {
    res.status(204).end();
    return true;
  }
  return false;
}

/** Une query string y cuerpo JSON en un único objeto de parámetros. */
function parametros(req) {
  let cuerpo = {};
  if (req.method === 'POST') {
    if (typeof req.body === 'string') {
      try {
        cuerpo = JSON.parse(req.body || '{}');
      } catch {
        cuerpo = {};
      }
    } else {
      cuerpo = req.body || {};
    }
  }
  return { ...(req.query || {}), ...cuerpo };
}

function normalizarFiltros(f) {
  if (!f || typeof f !== 'object') return null;
  const out = {};
  if (f.materia) out.materia = String(f.materia);
  if (f.tipo_norma) out.tipo_norma = String(f.tipo_norma);
  return Object.keys(out).length ? out : null;
}

export { cors, preflight, parametros, normalizarFiltros };
