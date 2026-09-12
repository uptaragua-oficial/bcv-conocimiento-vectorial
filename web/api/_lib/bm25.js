/**
 * Recuperación BM25 en JavaScript puro (sin dependencias).
 *
 * Se usa en el modo nativo de Vercel: la evaluación del corpus jurídico mostró
 * que BM25 fue la estrategia con mejor nDCG@5 (0.863) frente a la semántica
 * (0.524) y la híbrida (0.844), por lo que es una base sólida y honesta para
 * un despliegue sin servidor dedicado.
 */
const K1 = 1.2;
const B = 0.75;

/** Tokeniza normalizando acentos y descartando ruido. */
function tokenizar(texto) {
  return (
    (texto || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .match(/[a-z0-9]{2,}/g) || []
  );
}

/** Construye el índice invertido y las estadísticas de longitud. */
function construir(docs) {
  const df = new Map();
  const tf = new Array(docs.length);
  const dl = new Array(docs.length);

  for (let i = 0; i < docs.length; i++) {
    const tokens = tokenizar(docs[i][6]);
    dl[i] = tokens.length || 1;
    const f = new Map();
    for (const w of tokens) f.set(w, (f.get(w) || 0) + 1);
    tf[i] = f;
    for (const w of f.keys()) df.set(w, (df.get(w) || 0) + 1);
  }

  const suma = dl.reduce((a, b) => a + b, 0);
  return { docs, tf, dl, df, n: docs.length, avgdl: suma / (docs.length || 1) };
}

/** IDF con suavizado (siempre positivo). */
function idf(indice, termino) {
  const d = indice.df.get(termino) || 0;
  return Math.log(1 + (indice.n - d + 0.5) / (d + 0.5));
}

/** Convierte una fila del corpus en el objeto que consume el frontend. */
function fila(doc, score) {
  return {
    doc_id: doc[0],
    titulo: doc[1],
    seccion: doc[2],
    tipo_norma: doc[3],
    materia: doc[4],
    fuente_url: doc[5],
    texto: doc[6],
    entidades: doc[7] || [],
    score: Number(score.toFixed(4)),
  };
}

/**
 * Busca los fragmentos más relevantes.
 * @param {object} indice  resultado de `construir`
 * @param {string} consulta
 * @param {{limit?:number, filtros?:object}} opciones
 */
function buscar(indice, consulta, opciones = {}) {
  const limit = Math.min(Math.max(opciones.limit || 5, 1), 50);
  const filtros = opciones.filtros || null;
  if (!tokenizar(consulta).length) return [];

  const scores = puntajesBm25(indice, consulta);
  return mejores(indice, scores, limit, filtros);
}

/** Puntajes BM25 crudos de todos los documentos (sin filtrar ni ordenar). */
function puntajesBm25(indice, consulta) {
  const scores = new Float64Array(indice.n);
  for (const t of tokenizar(consulta)) {
    const peso = idf(indice, t);
    if (peso <= 0) continue;
    for (let i = 0; i < indice.n; i++) {
      const f = indice.tf[i].get(t);
      if (!f) continue;
      const norma = 1 - B + (B * indice.dl[i]) / indice.avgdl;
      scores[i] += (peso * (f * (K1 + 1))) / (f + K1 * norma);
    }
  }
  return scores;
}

/** Filtra, ordena y devuelve los `limit` mejores a partir de unos puntajes. */
function mejores(indice, scores, limit, filtros) {
  const candidatos = [];
  for (let i = 0; i < indice.n; i++) {
    if (!(scores[i] > 0)) continue;
    if (filtros) {
      const d = indice.docs[i];
      if (filtros.materia && d[4] !== filtros.materia) continue;
      if (filtros.tipo_norma && d[3] !== filtros.tipo_norma) continue;
    }
    candidatos.push([i, scores[i]]);
  }
  candidatos.sort((a, b) => b[1] - a[1]);
  return candidatos.slice(0, limit).map(([i, s]) => fila(indice.docs[i], s));
}

/** Valores disponibles para los filtros. */
function catalogo(indice) {
  const materias = new Set();
  const tipos = new Set();
  for (const d of indice.docs) {
    if (d[4]) materias.add(d[4]);
    if (d[3]) tipos.add(d[3]);
  }
  return {
    materias: [...materias].sort(),
    tipos_norma: [...tipos].sort(),
  };
}

export { tokenizar, construir, buscar, puntajesBm25, mejores, catalogo, fila };
