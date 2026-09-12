/**
 * Re-export para despliegues con la raíz del repositorio como Root Directory.
 *
 * Se usa CommonJS con import dinámico para no depender de un package.json en
 * la raíz: el handler real vive en `web/api/chat.js` (ESM). Si en Vercel se
 * configura Root Directory = `web`, se usa aquel directamente.
 */
module.exports = async (req, res) => {
  const { default: handler } = await import('../web/api/chat.js')
  return handler(req, res)
}
