/**
 * Asistente RAG del portal (modo nativo de Vercel).
 *
 * - Recupera fragmentos con BM25 (ver `corpus.js`).
 * - Compone la respuesta citando las fuentes.
 * - Si hay clave de un LLM, redacta con él; si no, responde en modo extractivo.
 *   Mismas salvaguardas que el backend Python: informa (no asesora) y toda
 *   afirmación se sustenta en la fuente.
 *
 * Proveedores soportados (API compatible con OpenAI, se elige por prioridad):
 *   1. DeepSeek   → DEEPSEEK_API_KEY   (modelo por defecto: deepseek-chat)
 *   2. Groq       → GROQ_API_KEY       (modelo por defecto: openai/gpt-oss-120b)
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

/** Devuelve la configuración del proveedor de LLM disponible, o null. */
function proveedorLLM() {
  if (process.env.DEEPSEEK_API_KEY) {
    const base = (process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com').replace(/\/+$/, '')
    return {
      nombre: 'deepseek',
      url: `${base}/chat/completions`,
      // .trim() por si la clave se pegó con un espacio o salto de línea final:
      // es la causa más común de un 401 en variables de entorno.
      clave: (process.env.DEEPSEEK_API_KEY || '').trim(),
      // Modelos vigentes: deepseek-flash | deepseek-v4-pro
      modelo: (process.env.DEEPSEEK_MODEL || 'deepseek-flash').trim(),
      // El modo "thinking" viene activado por defecto (esfuerzo alto): añade
      // latencia y anula `temperature`. Para un asistente con contexto
      // recuperado se desactiva por defecto.
      thinking: (process.env.DEEPSEEK_THINKING || 'disabled').trim(),
    }
  }
  if (process.env.GROQ_API_KEY) {
    return {
      nombre: 'groq',
      url: 'https://api.groq.com/openai/v1/chat/completions',
      clave: (process.env.GROQ_API_KEY || '').trim(),
      modelo: (process.env.GROQ_MODEL || 'openai/gpt-oss-120b').trim(),
    }
  }
  return null
}

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

async function generarLLM(proveedor, mensaje, contexto, historial) {
  const cuerpo = {
    model: proveedor.modelo,
    max_tokens: 900,
    messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        ...historialMensajes(historial),
        { role: 'user', content: `CONTEXTO:\n${contexto}\n\nPREGUNTA: ${mensaje}` },
    ],
  }

  if (proveedor.nombre === 'deepseek') {
    // El modo thinking (activo por defecto en DeepSeek) ignora `temperature`;
    // se envía solo cuando está desactivado.
    if (proveedor.thinking !== 'enabled') cuerpo.temperature = 0.1
    cuerpo.thinking = { type: proveedor.thinking === 'enabled' ? 'enabled' : 'disabled' }
  } else {
    cuerpo.temperature = 0.1
  }

  const resp = await fetch(proveedor.url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${proveedor.clave}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(cuerpo),
  })
  if (!resp.ok) {
    // Incluir el cuerpo del error: la API explica el motivo (clave inválida,
    // modelo inexistente, sin saldo…), mucho más útil que solo el código.
    let detalle = '';
    try {
      detalle = (await resp.text()).replace(/\s+/g, ' ').slice(0, 300);
    } catch {
      /* sin cuerpo */
    }
    const pista =
      resp.status === 401
        ? ' · revisa que la clave sea correcta y no tenga espacios al final'
        : '';
    throw new Error(`${proveedor.nombre} HTTP ${resp.status}${detalle ? ` · ${detalle}` : ''}${pista}`);
  }
  const data = await resp.json();
  return (data.choices?.[0]?.message?.content || '').trim();
}

async function chat({ mensaje, resultados, historial }) {
  const contexto = construirContexto(resultados);
  const proveedor = proveedorLLM();
  let respuesta;
  let modo = 'extractivo';
  let modelo = null;

  if (proveedor) {
    try {
      respuesta = await generarLLM(proveedor, mensaje, contexto, historial);
      modo = proveedor.nombre;
      modelo = proveedor.modelo;
    } catch (e) {
      respuesta = `[No se pudo contactar el modelo de lenguaje (${proveedor.nombre}): ${e.message}]\n\n${respuestaExtractiva(resultados)}`;
    }
  } else {
    respuesta = respuestaExtractiva(resultados);
  }

  return {
    respuesta,
    citas: construirCitas(resultados),
    modo_generacion: modo,
    modelo,
    n_fragmentos: resultados.length,
    disclaimer: DISCLAIMER,
  };
}

export {
  chat,
  construirContexto,
  construirCitas,
  respuestaExtractiva,
  proveedorLLM,
  DISCLAIMER,
};
