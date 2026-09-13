# Reordenación con cross-encoder (rerank)

Un cross-encoder lee **la consulta y el fragmento juntos** y puntúa cuánto
responde ese fragmento a esa pregunta. Es más caro que comparar vectores, pero
mucho más preciso, porque no depende de que ambos textos se parezcan: depende de
que uno responda al otro.

Es la pieza que faltaba para que el portal conteste bien la consulta que originó
todo este trabajo:

> «¿Qué requisitos exige el BCV para ser operador cambiario autorizado?»

---

## 1. El problema que resuelve

Al ampliar el corpus de 2 083 a 2 664 fragmentos entraron 563 fragmentos nuevos,
en su mayoría formularios e instructivos de la Gerencia de Operaciones
Cambiarias que repiten «operador cambiario» muchas veces. El **Art. 12** del
Convenio Cambiario N.º 1 —el artículo que dice quién puede ser operador
cambiario— pasó de estar en el top-5 a caer al puesto 28 en esa consulta.

La causa es de ranking, no de contenido: BM25 premia la repetición de términos y
un formulario que menciona «operador cambiario» veinte veces gana a un artículo
que lo menciona dos. Un cross-encoder no se deja engañar: puntúa la respuesta,
no la coincidencia.

### El rerank solo reordena lo que recibe

Este es el hallazgo que cambió el diseño. Con la fusión en `alpha = 0.5`, el
Art. 12 **no entraba ni siquiera entre los 20 primeros candidatos**, así que
ningún reranker podía rescatarlo: no estaba en la lista. Al subir a `alpha = 0.7`
entra (puesto 20 de 30) y el cross-encoder lo coloca **3.º**.

Por eso el valor por defecto de la fusión es ahora **0.7** y no 0.5, y por eso
está fijado en el código con su justificación, no en un archivo de configuración
que nadie lee.

---

## 2. Cómo se ejecuta en cada modo

### Modo B — backend dedicado (el modelo en local)

`src/search.py` carga `BAAI/bge-reranker-v2-m3` con `sentence-transformers` y
reordena. Usa la GPU si `torch.cuda.is_available()`, y si no, la CPU. Basta con
`rerank=true` en `/search` o `/chat`.

```bash
curl -X POST http://localhost:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"requisitos para ser operador cambiario","rerank":true,"limit":5}'
```

### Modo A — nativo de Vercel (el modelo **no** cabe)

El modelo pesa 2,2 GB en fp32 y el límite de una función serverless de Vercel es
250 MB sin comprimir. Además, cada consulta exige evaluar ~30 pares
(consulta, fragmento) en CPU: **16,3 segundos por consulta** medidos, muy por
encima de lo razonable.

Así que en Modo A el rerank se **delega en un proveedor externo** mediante el
formato estándar de la industria (lo usan Jina, Cohere, Voyage y Text Embeddings
Inference):

```
POST {RERANK_API_URL}
{ "model": "...", "query": "...", "documents": ["...", "..."], "top_n": 5 }

→ { "results": [ { "index": 3, "relevance_score": 0.87 }, … ] }
```

El `index` es la posición en el arreglo `documents` que se envió, y sirve para
reordenar los candidatos originales conservando sus metadatos y sus citas.

**Es opcional y nunca rompe nada.** Si no hay `RERANK_API_URL`, o el proveedor
devuelve un error, un JSON ilegible o una lista vacía, se conserva el orden de
la búsqueda híbrida. Está cubierto con diez pruebas (`web/tests/rerank.test.mjs`).

---

## 3. Qué se midió

Corpus de 2 664 fragmentos. El conjunto *silver* tiene 40 consultas aquí (en las
tablas de modelos se usa el de 150).

### El rerank no degrada la recuperación

| Estrategia | recall@5 | MRR | nDCG@5 | ms/consulta |
|---|---:|---:|---:|---:|
| sin rerank (α=0.5) | 0.950 | 0.906 | **0.917** | — |
| rerank sobre α=0.5 | 0.975 | 0.898 | 0.917 | 16 274 |
| rerank sobre RRF | 0.975 | 0.884 | 0.907 | 15 265 |

El nDCG@5 queda igual y el recall sube. No hay penalización.

### El Art. 12 vuelve al top-5 en las siete formulaciones

Puesto del artículo tras reordenar 20 candidatos:

| Consulta | α=0.5 | **α=0.7** | RRF | unión |
|---|---:|---:|---:|---:|
| «¿Qué requisitos exige el BCV para ser operador cambiario autorizado?» | >20 | **3** | 3 | 3 |
| «¿Cuáles son los requisitos para ser operador cambiario autorizado?» | 2 | **3** | 4 | 4 |
| «¿Quiénes pueden ser operadores cambiarios?» | 1 | **1** | 1 | 2 |
| «requisitos para operar como operador cambiario» | 2 | **2** | 2 | 3 |
| «qué se necesita para ser banco operador cambiario autorizado» | 1 | **1** | 1 | 1 |
| «quién puede actuar como operador cambiario en Venezuela» | 1 | **1** | 1 | 1 |
| «autorización para actuar como operador cambiario» | 1 | **1** | 1 | 1 |

| Generador de candidatos + rerank | Art. 12 en top-5 |
|---|---:|
| α=0.5 | 6/7 |
| **α=0.7** | **7/7** |
| RRF (k=60, α=0.5) | 7/7 |
| unión BM25 + densa | 7/7 |

Sin rerank, los mismos generadores daban 3/7 (α=0.5) y 5/7 (α=0.7).

**Conclusión:** una vez que el artículo está entre los candidatos, el
cross-encoder lo rescata y da casi igual cómo se generaron. Lo que importa es
que **esté** en la lista, y eso es lo que arregla α=0.7.

---

## 4. Configuración

| Variable | Por defecto | Para qué |
|---|---|---|
| `RERANK_API_URL` | *(vacío)* | Endpoint del proveedor. Sin esto no hay rerank |
| `RERANK_API_KEY` | *(vacío)* | Clave, si el proveedor la pide |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Modelo a solicitar |
| `RERANK_CANDIDATOS` | `30` | Candidatos a recuperar antes de reordenar (se acota a 10–100) |
| `RERANK_ACTIVO` | `true` | `false` lo desactiva aunque haya proveedor |
| `HYBRID_ALPHA` | `0.7` | Peso de lo semántico en la fusión (solo backend Python) |

El rerank se aplica **por defecto cuando hay proveedor configurado**. Se puede
desactivar por petición con `"rerank": false`, y en Modo A `/api/health` y
`/api/catalogo` informan de si está activo y con qué modelo; el portal muestra
entonces la etiqueta **Rerank** en la cabecera.

### Qué proveedor elegir

Cualquiera que hable el formato estándar. Jina ofrece
`jina-reranker-v2-base-multilingual` con capa gratuita, y es la vía más rápida de
probar. Un **Text Embeddings Inference (TEI)** propio sobre el Modo B evita
depender de terceros y es la opción coherente si el BCV despliega el backend en
su propia infraestructura.

**Costo orientativo:** ~30 documentos de ~500 tokens por consulta. En Jina o
Cohere, del orden de centésimas de dólar por cada mil consultas.

---

## 5. Verificar

```bash
# 1. Estado: debe decir rerank disponible
curl https://<tu-app>.vercel.app/api/health | grep -o '"rerank":[a-z]*'

# 2. La búsqueda debe devolver rerank: true
curl -s -X POST https://<tu-app>.vercel.app/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"requisitos para ser operador cambiario","limit":5}' \
  | grep -o '"rerank":[a-z]*'
```

En Modo B, el puesto de un fragmento concreto ante varias formulaciones se
comprueba con:

```bash
python -m scripts.verificar_consulta \
  --patron "Quedan autorizados para actuar" \
  --consulta "requisitos para ser operador cambiario autorizado"
```

### Si algo falla

| Síntoma | Causa probable |
|---|---|
| `/api/health` con `"rerank": false` | Falta `RERANK_API_URL` o `RERANK_ACTIVO=false` |
| `[rerank] HTTP 401` | Clave ausente o incorrecta |
| `[rerank] HTTP 404` | El modelo no existe en ese proveedor |
| `[rerank] respuesta sin resultados` | El proveedor no usa el formato estándar |
| Los resultados empeoran | Baja `RERANK_CANDIDATOS` o pon `"rerank": false` |

---

## 6. Lo que el rerank **no** resuelve

El corpus **no contiene** la norma que fija los requisitos para ser operador
cambiario. El Art. 12 solo dice *quién* puede serlo —los bancos universales
regidos por la Ley de Instituciones del Sector Bancario— y remite a
autorizaciones conjuntas del Ministerio de Finanzas y del BCV. De los 563
fragmentos nuevos, 142 mencionan «operador cambiario» y **ninguno** menciona
requisitos de autorización.

Ningún algoritmo de ordenación puede responder algo que no está en el corpus.
Para eso hay que **incorporar las fuentes que faltan**: Gaceta Oficial y
SUDEBAN. El rerank garantiza que, cuando el fragmento exista, aparezca.
