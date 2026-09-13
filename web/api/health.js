/**
 * GET /api/health — estado del modo nativo de Vercel.
 *
 * Incluye un diagnóstico **seguro** de las claves: no expone su valor, solo si
 * el formato parece correcto. Detecta el error más común al configurar el
 * portal: guardar una clave de otro proveedor, o pegarla incompleta, en la
 * variable equivocada.
 */
import { totalFragmentos, vectoresAlineados } from './_lib/corpus.js'
import { embeddingsConfig, semanticaDisponible, metaVectores } from './_lib/embeddings.js'
import { rerankConfig, rerankDisponible } from './_lib/rerank.js'
import { diagnosticoLLM } from './_lib/rag.js'
import { preflight } from './_lib/http.js'

export default function handler(req, res) {
  if (preflight(req, res)) return

  const emb = embeddingsConfig()
  const meta = metaVectores()
  const rr = rerankConfig()
  // La semántica solo está operativa si hay clave Y los vectores corresponden
  // al corpus actual.
  const semantica = semanticaDisponible() && vectoresAlineados()
  const rerank = rerankDisponible()
  return res.status(200).json({
    status: 'ok',
    modo: 'vercel-serverless',
    motor: semantica ? 'hibrido' : 'bm25',
    recuperacion: semantica ? 'hibrida' : 'keyword',
    rerank,
    coleccion: 'Normativa',
    objetos: totalFragmentos(),
    embeddings_modelo: emb ? emb.modelo : null,
    vectores: meta
      ? { n: meta.n, dim: meta.dim, modelo: meta.modelo, alineados: vectoresAlineados() }
      : null,
    rerank_config: rr ? { modelo: rr.modelo, candidatos: rr.candidatos } : null,
    llm: diagnosticoLLM(),
  })
}
