# Comparativa de modelos de embeddings

Medición **real** sobre el corpus jurídico del BCV (2 083 fragmentos), con el
mismo conjunto de 40 consultas para todos los modelos, derivado de forma
determinista (semilla fija) para que la comparación sea justa.

- **k = 5**
- Métricas: recall@5, MRR y nDCG@5
- Reproducible con:
  `python -m scripts.comparar_recuperacion --conjunto … --conjunto …`

---

## Resultados

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 (léxico) | 0.900 | 0.796 | 0.821 |
| BGE-M3 · densa | 0.725 | 0.568 | 0.607 |
| **BGE-M3 · híbrida** | **0.975** | **0.850** | **0.881** |
| e5-large · densa | 0.600 | 0.456 | 0.492 |
| e5-large · híbrida | 0.925 | 0.828 | 0.852 |

*(pendiente: fila de OpenAI con `text-embedding-3-small`, ejecutable desde Colab
con `--api`)*

---

## Qué dicen los números

### 1. La búsqueda híbrida sí mejora — y bastante

| | BM25 solo | BGE-M3 híbrida | Diferencia |
|---|---:|---:|---:|
| recall@5 | 0.900 | **0.975** | **+0.075** |
| nDCG@5 | 0.821 | **0.881** | +0.060 |

Es la conclusión más importante: **combinar lo léxico con lo semántico supera a
cualquiera de los dos por separado**. Vale la pena activar los embeddings.

### 2. La búsqueda densa sola es *peor* que BM25

Un resultado contraintuitivo pero consistente: BGE-M3 densa (0.607) y e5 densa
(0.492) quedan **por debajo** de BM25 (0.821). Tiene sentido en un corpus
jurídico: los términos exactos («Artículo 31», «encaje legal», siglas) pesan
mucho, y el vocabulario es muy específico.

**Implicación práctica:** nunca conviene activar solo la búsqueda semántica;
siempre híbrida con `alpha ≈ 0.5`.

### 3. BGE-M3 es mejor modelo que e5-large

- Híbrida: **0.881 vs 0.852**
- Densa: **0.607 vs 0.492**

BGE-M3 gana en las dos. Es coherente con que sea un modelo más reciente y
específicamente orientado a recuperación multilingüe.

### 4. Pero e5-large cuesta cero fricción

| Modelo | Proveedor en ejecución | Qué hace falta |
|---|---|---|
| BGE-M3 | DeepInfra (`BAAI/bge-m3`) | Crear cuenta gratuita |
| e5-large | HuggingFace | **El token que ya tienes** |

La diferencia (0.881 vs 0.852) es real pero modesta: **ambos superan a BM25**.

---

## Recomendación

| Situación | Elección |
|---|---|
| Quieres el máximo rendimiento | **BGE-M3 híbrida** + DeepInfra |
| No quieres crear más cuentas | **e5-large híbrida** + tu token de HuggingFace |
| Ninguna de las dos te convence | BM25 (0.821): ya funciona y no depende de nadie |

En todos los casos el portal **cae a BM25 automáticamente** si el proveedor
falla, así que activar los embeddings no añade riesgo.

---

## Cómo añadir la fila de OpenAI

Desde Colab (que sale por una región admitida), con el vectorizador ya ejecutado:

```bash
python -m scripts.comparar_recuperacion \
  --vectores web/api/_data/vectors.f32 \
  --meta     web/api/_data/embeddings_meta.json \
  --nombre   openai-3-small \
  --api
```

Usa el mismo conjunto de 40 consultas, así que la comparación es directa.
