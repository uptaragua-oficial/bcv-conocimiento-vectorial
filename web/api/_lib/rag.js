/**
 * Asistente RAG del portal (modo nativo de Vercel).
 *
 * - Recupera fragmentos con BM25 (ver `corpus.js`).
 * - Compone la respuesta citando las fuentes.
 * - Si existe `GROQ_API_KEY`, redacta con un LLM; si no, responde en modo
 *   extractivo. Mismas salvaguardas que el backend Python:
 *   informa (no asesora) y toda afirmación se sustenta en la fuente.
 */
const DISCLAIMER =
  'Este asistente entrega información normativa de fuentes públicas del BCV y no presta asesoría legal ni financiera. Verifique siempre el texto oficial.';

const SYSTEM_PROMPT = `Eres un asistente especializado en la normativa del Banco Central \
de Venezuela (BCV). Respondes a consultas sobre leyes, resoluciones, convenios \
cambiarios, circulares y actos administrativos.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con la información contenida en el CONTEXTO entregado.
2. Si el contexto no contiene la respuesta, dilo con claridad y sugiere reformular.
3. Cita las fuentes con corchetes al final de cada afirmación: [1], [2], etc.
4. No inventes números de artículos, fechas ni disposiciones.
5. No prestas asesoría legal ni financiera; solo informas sobre el texto normativo.
6. Responde en español, de forma clara, breve y ordenada.`;

const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';

function construirContexto(resultados) {
  return resultados
    .map((r, i) => {
      let cab = `[${i + 1}] ${r.tipo_norma || 'Norma'}`;
      if (r.seccion) cab += ` — ${r.seccion}`;
      if (r.materia) cab += ` (materia: ${r.materia})`;
      return `${cab}\n${(r.texto || '').trim()}`;
    })
    .join('\n\n---\n\n');
}

function construirCitas(resultados) {
  return resultados.map((r, i) => ({
    n: i + 1,
    titulo: r.titulo,
    seccion: r.seccion,
    tipo_norma: r.tipo_norma,
    materia: r.materia,
    fuente_url: r.fuente_url,
    fragmento: (r.texto || '').slice(0, 600),
    score: r.score,
    entidades: r.entidades || [],
  }));
}

function historialMensajes(historial) {
  return (historial || []).slice(-6).map((h) => ({
    role: h.rol === 'assistant' || h.rol === 'bot' ? 'assistant' : 'user',
    content: String(h.contenido || '').trim(),
  })).filter((m) => m.content);
}

function respuestaExtractiva(resultados) {
  if (!resultados.length) {
    return 'No encontré normativa en el corpus que responda a esa consulta. Intenta reformularla o quitar los filtros aplicados.';
  }
  const partes = [
    'Estos son los fragmentos normativos más relevantes que encontré en el corpus jurídico del BCV para tu consulta:\n',
  ];
  resultados.slice(0, 3).forEach((r, i) => {
    let etiqueta = r.tipo_norma || 'Norma';
    if (r.seccion) etiqueta += ` — ${r.seccion}`;
    const texto = (r.texto || '').trim().replace(/\s+/g, ' ');
    partes.push(`**[${i + 1}] ${etiqueta}:** «${texto.slice(0, 420)}…»`);
  });
  partes.push(
    '\n\n_Modo extractivo (sin modelo de lenguaje): se muestran los fragmentos recuperados con su fuente. Configure `GROQ_API_KEY` para obtener respuestas redactadas._'
  );
  return partes.join('\n\n');
}

async function generarGroq(mensaje, contexto, historial) {
  const resp = await fetch(GROQ_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.GROQ_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: process.env.GROQ_MODEL || 'openai/gpt-oss-120b',
      temperature: 0.1,
      max_tokens: 900,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        ...historialMensajes(historial),
        { role: 'user', content: `CONTEXTO:\n${contexto}\n\nPREGUNTA: ${mensaje}` },
      ],
    }),
  });
  if (!resp.ok) throw new Error(`Groq HTTP ${resp.status}`);
  const data = await resp.json();
  return (data.choices?.[0]?.message?.content || '').trim();
}

async function chat({ mensaje, resultados, historial }) {
  const contexto = construirContexto(resultados);
  let respuesta;
  let modo = 'extractivo';

  if (process.env.GROQ_API_KEY) {
    try {
      respuesta = await generarGroq(mensaje, contexto, historial);
      modo = 'groq';
    } catch (e) {
      respuesta = `[No se pudo contactar el modelo de lenguaje: ${e.message}]\n\n${respuestaExtractiva(resultados)}`;
    }
  } else {
    respuesta = respuestaExtractiva(resultados);
  }

  return {
    respuesta,
    citas: construirCitas(resultados),
    modo_generacion: modo,
    modelo: modo === 'groq' ? process.env.GROQ_MODEL || 'openai/gpt-oss-120b' : null,
    n_fragmentos: resultados.length,
    disclaimer: DISCLAIMER,
  };
}

export { chat, construirContexto, construirCitas, respuestaExtractiva, DISCLAIMER };
