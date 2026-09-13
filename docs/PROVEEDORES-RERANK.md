# Proveedores de rerank: DeepInfra frente a Jina

El portal no ejecuta el cross-encoder: se lo pide a un proveedor por API
(ver [`RERANK.md`](RERANK.md)). Esta nota compara los dos candidatos y explica
por qué la configuración por defecto es **DeepInfra**.

> Todo lo que sigue está verificado contra la documentación y la API pública de
> cada proveedor en la fecha de la medición, no contra notas de prensa. Las
> fuentes están enlazadas.

---

## 1. Resumen

| | **DeepInfra** | **Jina AI** |
|---|---|---|
| Endpoint | `POST /v1/inference/{modelo}` | `POST /v1/rerank` |
| Dialecto | propio (`queries`/`scores`) | estándar (`query`/`results`) |
| Rerankers de texto | 3 (Qwen3-Reranker 0.6B / 4B / 8B) + 1 multimodal | v3.5, v2-base-multilingual, m0 (multimodal) |
| Modelo en la petición | en la **URL** | en el **cuerpo** |
| Precio publicado | **sí**, por token | no en la web pública (requiere cuenta) |
| Facturación mínima | no | **10 000 tokens por petición** |
| Límite de tasa | **200 peticiones concurrentes por modelo** | 100 RPM y 100 000 TPM (nivel gratuito) |
| Contexto por documento | hasta 32 768 tokens | 1 024 tokens en v2-base (con troceado) |
| Sirve también embeddings | **sí** (§6) | sí |
| Calidad medida en este cuerpo | **6/7** con su modelo más barato (§5) | **7/7** con `jina-reranker-v3.5` en el portal desplegado |

**Recomendación: DeepInfra.** Por tres razones concretas, no por preferencia.

---

## 2. Precio: DeepInfra lo publica, Jina no

DeepInfra factura **solo tokens de entrada**, sin mínimo por petición, y el
precio es público. Obtenido de su API de modelos
([`api.deepinfra.com/models/list`](https://api.deepinfra.com/models/list),
campo `pricing.cents_per_input_token`):

| Modelo | Precio | Contexto |
|---|---:|---:|
| `Qwen/Qwen3-Reranker-0.6B` | **$0,010 / 1M tokens** | 32 768 |
| `Qwen/Qwen3-Reranker-4B` | **$0,025 / 1M tokens** | 32 768 |
| `Qwen/Qwen3-Reranker-8B` | **$0,050 / 1M tokens** | 32 768 |
| `nvidia/llama-nemotron-rerank-vl-1b-v2` | $0,010 / 1M tokens | 10 240 |

Jina no publica su tarifa por token en la web abierta
([jina.ai/reranker](https://jina.ai/reranker/)): ofrece «tokens gratuitos para
empezar» y «paquetes de tokens» cuyo precio aparece en el panel tras
autenticarse. Sí documenta que **cada petición de rerank cuesta un número fijo de
tokens, a partir de 10 000**. Es decir: aunque pidas 5 documentos cortos, se
facturan 10 000 tokens.

### Qué cuesta nuestro caso concreto

Una consulta del portal envía **30 candidatos de ~500 tokens** ≈ 15 000 tokens.

| | Cálculo | Coste por 1 000 consultas |
|---|---|---:|
| DeepInfra · Qwen3-Reranker-0.6B | 15 000 × $0,010/1M | **$0,15** |
| DeepInfra · Qwen3-Reranker-8B | 15 000 × $0,050/1M | **$0,75** |
| Jina | 15 000 tokens es superior al mínimo de 10 000, así que no hay desperdicio… pero el precio unitario no es público | — |

En cualquier caso hablamos de **menos de un dólar por mil consultas**. El coste
no es el criterio de decisión; la previsibilidad sí lo es: con DeepInfra se sabe
lo que se paga antes de contratar.

---

## 3. Límites: el criterio que decide

**DeepInfra** limita **peticiones concurrentes**, no peticiones por minuto:

> «Cada cuenta tiene un límite por defecto de **200 peticiones concurrentes por
> modelo**. Si consultas dos modelos a la vez, puedes atender 400 peticiones
> concurrentes. Este límite es suficiente para la mayoría de aplicaciones en
> producción, incluidas las que tienen cientos de miles de usuarios activos
> diarios.»
> — [docs.deepinfra.com/account/rate-limits](https://docs.deepinfra.com/account/rate-limits)

Como nuestro rerank tarda del orden de décimas de segundo, 200 concurrentes son
un techo altísimo. Al excederlo devuelve **429**, previsible y reintentable.

**Jina** limita por **peticiones por minuto y tokens por minuto**:

| Nivel | Límite |
|---|---|
| Gratuito | 100 RPM y 100 000 TPM |
| Siguiente | 500 RPM y 2 000 000 TPM |
| Superior | 5 000 RPM y 50 000 000 TPM |

Traducido a nuestro caso: a 15 000 tokens por consulta, el nivel gratuito de
Jina da **100 000 / 15 000 ≈ 6 consultas por minuto**. Es un techo que se alcanza
con muy poco tráfico, y obliga a razonar en dos dimensiones (peticiones *y*
tokens) en vez de una.

---

## 4. Modelos

**DeepInfra** ofrece la familia **Qwen3-Reranker** completa —0.6B, 4B y 8B— más
un reranker multimodal de NVIDIA. Poder subir de 0.6B a 8B **cambiando una
variable de entorno** y pagando 5 veces más por token es exactamente la palanca
que se quiere tener cuando el corpus crece.

**Jina** ofrece `jina-reranker-v3.5` (0.6B, context window de 131K, listwise),
`jina-reranker-v2-base-multilingual` y `jina-reranker-m0` (multimodal). El
contexto largo es una ventaja real si algún día se rerankean documentos enteros
en vez de fragmentos; **hoy no lo hacemos**: nuestros fragmentos son de ~500
tokens y se recortan a 2 000 caracteres antes de enviarlos.

Conviene saber que `BAAI/bge-reranker-v2-m3` y `jina-reranker-v2-base-multilingual`
**no aparecen** en el catálogo de rerankers de DeepInfra: allí los modelos
disponibles son los Qwen3 y el de NVIDIA. Si se configura DeepInfra, el modelo
por defecto del cliente pasa a ser `Qwen/Qwen3-Reranker-0.6B`.

---

## 5. Medición sobre nuestro corpus

Las fichas de los proveedores dicen qué modelos ofrecen; no dicen cómo se
comportan con **el corpus jurídico del BCV**. Eso se mide.

Metodología: 2 664 fragmentos, fusión híbrida con α=0.7, **20 candidatos** por
consulta (que es lo que vería el reranker en producción) y dos cross-encoders
ejecutados en local —sin API— sobre exactamente los mismos candidatos. La
pregunta es si el artículo conocido (Art. 12 del Convenio Cambiario N.º 1)
queda entre los cinco primeros que se enviarían al modelo de lenguaje.

| Consulta real | `bge-reranker-v2-m3` | `Qwen3-Reranker-0.6B` |
|---|---:|---:|
| «¿Qué requisitos exige el BCV para ser operador cambiario autorizado?» | 3 | **1** |
| «¿Cuáles son los requisitos para ser operador cambiario autorizado?» | 3 | **1** |
| «¿Quiénes pueden ser operadores cambiarios?» | 1 | 1 |
| «requisitos para operar como operador cambiario» | **2** | 6 |
| «qué se necesita para ser banco operador cambiario autorizado» | **1** | 2 |
| «quién puede actuar como operador cambiario en Venezuela» | 1 | 1 |
| «autorización para actuar como operador cambiario» | 1 | 1 |
| **En el top-5** | **7/7** | **6/7** |

Y sobre el conjunto *silver* de 40 consultas, con los mismos candidatos:

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| sin rerank (α=0.7) | 0.9750 | 0.9021 | 0.9206 |
| `bge-reranker-v2-m3` | 0.9750 | **0.9100** | **0.9259** |

**Lectura.** El modelo **más barato de DeepInfra** (`Qwen3-Reranker-0.6B`,
$0,010/1M) rinde al mismo nivel que `bge-reranker-v2-m3`, que es el cross-encoder
de referencia en multilingüe: empata en 6 de 7 consultas y en la consulta
original que motivó todo el trabajo lo coloca **primero**. Es un argumento fuerte
para DeepInfra: su opción más económica no obliga a renunciar a calidad, y por
encima quedan 4B y 8B si se quiere apretar más.

**Sobre la velocidad.** En CPU, `bge-reranker-v2-m3` procesa ~1,2 pares/s y
`Qwen3-Reranker-0.6B` ~0,3 pares/s: al ser generativo, calcular sus logits sobre
un vocabulario de 151k tokens por par es mucho más caro. Es irrelevante para la
decisión —en producción el cómputo lo hace el proveedor— pero explica por qué
esta comparación se hizo con 7 consultas reales y no con las 40 del conjunto
*silver*: 45 minutos por modelo en vez de 8.

**Lo que no se pudo medir.** `jina-reranker-v3.5` no se puede ejecutar en local,
así que su calidad no se midió aquí. **Sí se midió después, contra el portal ya
desplegado y con cuenta propia: 7/7**, el mismo resultado que `bge-reranker-v2-m3`
en local, con 337-502 ms por búsqueda. Ver [`RERANK.md`](RERANK.md).

> Es una diferencia práctica a tener en cuenta: un proveedor por API se puede
> **medir sin ejecutarlo**, atacando el despliegue real. Eso convierte la elección
> de proveedor en una comparación con datos propios y no en una apuesta.

## 6. La razón de fondo: una sola cuenta para todo

DeepInfra no solo sirve rerankers. En el mismo catálogo y con la misma clave
están los embeddings que ya usamos:

| Modelo de embeddings | Precio | Contexto |
|---|---:|---:|
| `intfloat/multilingual-e5-large` | $0,010 / 1M tokens | 512 |
| `BAAI/bge-m3` | $0,010 / 1M tokens | 8 192 |
| `Qwen/Qwen3-Embedding-8B` | $0,010 / 1M tokens | 32 768 |

Esto importa porque **`intfloat/multilingual-e5-large` es exactamente el modelo
con el que se vectorizó el corpus**: los 2 664 vectores de `vectors.f32` siguen
siendo válidos, solo cambia quién vectoriza la consulta en tiempo de ejecución.
Hoy eso depende del *router* de Hugging Face y de un token de HF; con una cuenta
de DeepInfra, **embeddings y rerank salen del mismo proveedor y la misma clave**.

Y hay una consecuencia de segundo orden: la comparativa de modelos descartó
`BAAI/bge-m3` por exigir precisamente una cuenta de DeepInfra. Si se abre la
cuenta de todos modos, **esa opción vuelve a estar sobre la mesa** (0.879 de
nDCG@5 híbrida frente a 0.877 de e5, empate técnico, pero con vectores de
contexto 8 192 en vez de 512).

---

## 7. La pega: el dialecto propio

DeepInfra no usa el formato estándar. Su endpoint es
`POST /v1/inference/{modelo}`, la consulta viaja como `queries` (arreglo), el
modelo va **en la ruta**, no admite `top_n` y devuelve `scores` **en el orden de
entrada y sin ordenar**. Un cliente escrito para Jina o Cohere no funciona contra
DeepInfra sin cambios.

Por eso `web/api/_lib/rerank.js` implementa **los dos dialectos** y deduce cuál
usar de la URL (o de `RERANK_FORMATO`). El caso delicado —`scores` alineado con
la entrada— tiene su propia comprobación: si la longitud no cuadra, se descarta
el rerank en lugar de asignar a cada fragmento el puntaje de otro.

Esto es lo que hace que la decisión no sea irreversible: **cambiar de proveedor
es cambiar una variable de entorno**, no reescribir código.

---

## 8. Configuración

```bash
# Vercel → Settings → Environment Variables
RERANK_API_URL=https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-0.6B
RERANK_API_KEY=<tu token de DeepInfra>
RERANK_CANDIDATOS=30
# Opcional: orientar la tarea al dominio jurídico
RERANK_INSTRUCTION=Dada una consulta sobre normativa del Banco Central de Venezuela, recupera los artículos que la responden
```

El formato se detecta solo (`deepinfra.com` en la URL). Para pasar al modelo de
8B basta con cambiar la URL a `…/inference/Qwen/Qwen3-Reranker-8B`.

Y para volver a Jina, sin tocar código:

```bash
RERANK_API_URL=https://api.jina.ai/v1/rerank
RERANK_API_KEY=<tu clave de Jina>
RERANK_MODEL=jina-reranker-v3.5
```

---

## 9. Fuentes

- [Reranking — DeepInfra](https://docs.deepinfra.com/apis/reranker) (endpoint, formato, `scores`)
- [Rate Limits — DeepInfra](https://docs.deepinfra.com/account/rate-limits) (200 concurrentes por modelo)
- [Catálogo de modelos — DeepInfra](https://api.deepinfra.com/models/list) (precios por token)
- [Embeddings — DeepInfra](https://docs.deepinfra.com/apis/embeddings) (API compatible con OpenAI)
- [Reranker API — Jina AI](https://jina.ai/reranker/) (endpoint, niveles de RPM/TPM, mínimo de 10 000 tokens, truncado por modelo)
