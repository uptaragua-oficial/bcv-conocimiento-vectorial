/**
 * Limpieza de claves leídas de variables de entorno.
 *
 * Pegar una clave en un panel web —Vercel, un `.env`, cualquier interfaz— es
 * una fuente inagotable de errores silenciosos: se cuela un salto de línea al
 * copiar, o se pega el valor **con las comillas** porque venía así de un
 * ejemplo. En ambos casos la clave es «casi» correcta y el proveedor responde
 * 401 sin explicar nada.
 *
 * Estaba resuelto solo para el LLM (`rag.js`), mientras que el rerank recortaba
 * espacios pero no comillas, y los embeddings no recortaban nada. Eso produce la
 * peor clase de fallo: funciona en una pieza del sistema y falla en otra, con el
 * mismo valor.
 *
 * Se centraliza aquí para que las tres rutas limpien igual.
 */

/** Quita espacios, saltos de línea y comillas envolventes de una clave. */
export function limpiarClave(valor) {
  return String(valor ?? '')
    .trim()
    .replace(/^["'`]+|["'`]+$/g, '')
    .trim()
}

/** Lee una variable de entorno y la limpia. Devuelve '' si no está definida. */
export function claveDeEntorno(nombre) {
  return limpiarClave(process.env[nombre])
}
