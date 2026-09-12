/** GET /api/health — estado del modo nativo de Vercel. */
import { totalFragmentos } from './_lib/corpus.js'
import { embeddingsConfig, semanticaDisponible, metaVectores } from './_lib/embeddings.js'
import { preflight } from './_lib/http.js'

export default function handler(req, res) {
  if (preflight(req, res)) return

  const emb = embeddingsConfig()
  const meta = metaVectores()
  return res.status(200).json({
    status: 'ok',
    modo: 'vercel-serverless',
    motor: semanticaDisponible() ? 'hibrido' : 'bm25',
    recuperacion: semanticaDisponible() ? 'hibrida' : 'keyword',
    coleccion: 'Normativa',
    objetos: totalFragmentos(),
    embeddings_modelo: emb ? emb.modelo : null,
    vectores: meta ? { n: meta.n, dim: meta.dim, modelo: meta.modelo } : null,
  })
}
