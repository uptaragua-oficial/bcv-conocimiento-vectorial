# Técnicas y métricas de búsqueda — Anexo técnico

Este documento explica **qué técnicas de recuperación se usaron** en la
Plataforma de Conocimiento Vectorial del BCV y **con qué métricas se midieron**.
Cada técnica y cada métrica se define en el propio texto, de modo que el
documento se pueda leer sin consultar otras fuentes.

Todas las cifras provienen de mediciones sobre el corpus real, no de
estimaciones. Al final se indica cómo reproducirlas y se detalla lo que **no** se
implementó, que es igual de importante.

---

## 1. El corpus sobre el que se busca

Antes de las técnicas conviene fijar la materia prima, porque condiciona todas
las decisiones.

| | |
|---|---|
| Documentos | 258 |
| Fragmentos (*chunks*) | 2 664 |
| Dimensión de los vectores | 1 024 |
| Campos por fragmento | 8 |

Los ocho campos son: `doc_id`, `titulo`, `seccion`, `tipo_norma`, `materia`,
`fuente_url`, `texto` y `entidades`. Los cinco centrales son **metadatos** y
permiten filtrar; los otros tres identifican y localizan el fragmento.

### 1.1 Extracción multi-formato

Los documentos del BCV llegan en HTML, PDF, DOCX y XLSX. La extracción convierte
cada uno a texto plano y **elimina el ruido de navegación** de la web del Banco
—menús, migas de pan, avisos de cookies—, que de otro modo acabaría dentro de los
fragmentos y ensuciaría las búsquedas.

### 1.2 Troceado estructural (*chunking*)

**Trocear** es partir cada documento en unidades más pequeñas, porque un vector
resume mal un documento entero: si se vectoriza una ley completa, el vector
representa el promedio de todos sus temas y no sirve para encontrar ninguno.

Aquí el corte **no es por número fijo de caracteres, sino por estructura
jurídica**: cada artículo es un fragmento. Es la unidad natural de consulta —un
abogado pregunta por el artículo 12, no por «los caracteres 4 000 a 5 800»— y
además hace que la cita sea exacta.

Los preámbulos, que no tienen artículos, se trocean aparte. Y cuando un artículo
excede **1 800 caracteres** se subdivide con un **solape de 200 caracteres**: el
solape repite el final de un fragmento al principio del siguiente para que una
frase partida no pierda su significado en ninguno de los dos.

### 1.3 Reconocimiento de entidades (NER)

El **NER** (*Named Entity Recognition*, reconocimiento de entidades nombradas)
consiste en detectar automáticamente en un texto las menciones a cosas concretas:
instituciones, monedas, períodos, instrumentos normativos.

Se aplicó con **GLiNER**, un modelo *zero-shot*: se le indican las categorías que
interesan («institución», «moneda», «período»…) y las reconoce **sin haber sido
entrenado específicamente para ellas**. Eso evita tener que etiquetar a mano
miles de fragmentos jurídicos.

El resultado se guarda en el campo `entidades` y sirve para **filtrar**: permite
pedir «solo fragmentos que mencionen el BCV y el mercado cambiario». Cuando el
modelo no está disponible, un conjunto de expresiones regulares hace de respaldo
para no detener el procesamiento.

> **Qué motor conviene para cada etiqueta no es obvio, y se midió.** Sobre 500
> fragmentos del corpus, GLiNER detecta el 0 % de los tipos de norma mientras las
> reglas alcanzan el 92 %, y en cambio aporta entidades que las reglas no tienen
> («divisas», «títulos valores»). El detalle y la combinación adoptada están en
> [`INFORME-NER.md`](INFORME-NER.md).

---

## 2. Técnicas de recuperación

### 2.1 Recuperación léxica: BM25

**Qué es.** BM25 (*Best Matching 25*) es un algoritmo de recuperación **léxica**:
compara las *palabras* de la consulta con las de cada fragmento. No entiende
significados; puntúa coincidencias.

Su puntaje para un fragmento combina tres ideas:

- **TF** (*term frequency*, frecuencia del término): cuantas más veces aparece
  una palabra de la consulta en el fragmento, más relevante es… pero con
  **saturación**. Repetir «operador» cincuenta veces no hace a un fragmento
  cincuenta veces más relevante; a partir de cierto punto deja de aportar. El
  parámetro **k1** controla esa saturación.
- **IDF** (*inverse document frequency*, frecuencia inversa en el corpus): una
  palabra poco común pesa más que una común. «Cambiario» discrimina; «de» no.
- **Normalización por longitud**: un fragmento largo tiene más ocasiones de
  contener una palabra, así que se penaliza. El parámetro **b** regula cuánto.

**Parámetros usados:** `k1 = 1.2`, `b = 0.75`. Son los valores habituales en
recuperación de información y no se modificaron.

**Lematización ligera por truncado.** Un problema real apareció aquí: la consulta
decía *operador · cambiario · autorizado* y el artículo *operadores · cambiarios ·
autorizados*. BM25 no los relaciona, porque para él son palabras distintas. La
solución fue **recortar cada palabra a sus 7 primeros caracteres**, lo que une
plurales y géneros del español (`autorizado` → `autoriz`, `autorizados` →
`autoriz`) **sin fusionar palabras distintas** (`autoridad` → `autorid`, que sigue
siendo diferente). Es una **lematización** —reducción de una palabra a su raíz—
deliberadamente simple: un lematizador completo habría exigido un diccionario y
más cómputo, y para español jurídico el truncado resuelve el caso.

**Coste:** el índice se construye una vez (entre 100 y 270 ms para 2 664
fragmentos, según la máquina y la carga) y cada consulta tarda **1 a 4 ms**.

### 2.2 Recuperación densa: *embeddings* y similitud coseno

**Qué es.** Un **embedding** o vector denso es una representación numérica del
significado de un texto: una lista de 1 024 números que sitúa el texto en un
espacio donde **cosas que significan lo mismo quedan cerca**, aunque se escriban
con palabras diferentes.

El modelo que produce esos vectores se llama **bi-encoder** porque codifica la
consulta y el documento **por separado**, cada uno por su lado. Eso es lo que
hace que sea rápido: los 2 664 fragmentos se vectorizan una sola vez, y en cada
consulta solo hay que vectorizar la pregunta y compararla. Su límite es que nunca
«lee» la consulta y el documento a la vez.

**Similitud coseno.** Para comparar dos vectores se mide el **coseno del ángulo
que forman**. Vale 1 si apuntan en la misma dirección y 0 si son perpendiculares.
Se usa el coseno y no la distancia euclídea porque interesa la *dirección*
(el significado), no la *magnitud*. Normalizando cada vector a longitud 1 —lo que
se hace al generarlos—, el coseno se reduce a un simple producto punto, que es
mucho más barato de calcular.

**Modelo usado:** `intfloat/multilingual-e5-large`, 1 024 dimensiones. Los
documentos se vectorizan con el prefijo `passage: ` y las consultas con
`query: `, porque el modelo fue entrenado así y omitir el prefijo degrada la
calidad de forma apreciable.

**El modelo debe ser el mismo en ambos lados.** Si los vectores del corpus se
calculan con un modelo y las consultas con otro, las distancias no significan
nada. El sistema lo comprueba y, si detecta el desajuste, **vuelve a BM25** en
lugar de devolver resultados incorrectos.

### 2.3 Índice HNSW

**Qué es.** Comparar la consulta contra 2 664 vectores uno por uno es viable;
hacerlo contra millones, no. **HNSW** (*Hierarchical Navigable Small World*) es un
índice **ANN** (*Approximate Nearest Neighbours*, vecinos más próximos
aproximados): en lugar de examinar todo, recorre un grafo de vecindades en varias
capas —las superiores son mapas gruesos, las inferiores son detallados— y
encuentra **casi siempre** el vecino más cercano en una fracción del tiempo.

**Aproximado** significa que puede no encontrar el óptimo absoluto. Es un
intercambio deliberado: se acepta una probabilidad pequeña de fallar a cambio de
pasar de segundos a milisegundos.

**Parámetros usados** (Weaviate 1.28):

| Parámetro | Valor | Qué controla |
|---|---:|---|
| `efConstruction` | 256 | Esfuerzo al **construir** el grafo. Más alto, mejor calidad del índice |
| `maxConnections` | 32 | Vecinos por nodo. Más conexiones, mejor recall y más memoria |
| `ef` | 128 | Esfuerzo en **cada consulta**. Más alto, mejor recall y más latencia |
| `dynamicEfFactor` | 2 | Ajusta `ef` automáticamente al número de resultados pedidos |

### 2.4 Búsqueda híbrida por fusión lineal

**Qué es.** La búsqueda **híbrida** combina las dos anteriores porque son buenas
en cosas distintas. BM25 acierta con términos exactos —«Artículo 31», siglas,
cifras— y falla cuando la consulta usa palabras que no aparecen en el texto. La
búsqueda densa hace lo contrario: entiende paráfrasis, pero se le escapan los
términos raros que son precisamente los que identifican una norma.

**Fusión lineal** significa combinar los dos puntajes con una suma ponderada.
Antes hay que **normalizarlos**, porque viven en escalas distintas: BM25 no tiene
cota superior y el coseno va de 0 a 1. Se divide cada lista por su máximo, de modo
que ambos queden entre 0 y 1, y se combinan:

```
puntaje = α · (coseno normalizado) + (1 − α) · (BM25 normalizado)
```

**El parámetro α** decide el peso de lo semántico: `α = 0` es solo BM25, `α = 1`
es solo densa. **Se usa α = 0.7**, y no es arbitrario: con 0.5 el Art. 12 del
Convenio Cambiario N.º 1 **no entraba ni entre los 20 primeros candidatos** para
la consulta sobre operadores cambiarios, y como el reranker solo puede reordenar
lo que recibe, no había forma de recuperarlo. Con 0.7 entra. El coste de ese
cambio en el conjunto de evaluación es de 0.002 de nDCG@5, dentro del error de
muestreo.

### 2.5 RRF (*Reciprocal Rank Fusion*)

**Qué es.** Otra forma de fusionar dos rankings que **ignora los puntajes y usa
solo las posiciones**. A cada documento se le asigna la suma de `1 / (k + puesto)`
en cada lista, con `k` habitualmente 60. La idea: un documento que aparece arriba
en **ambas** listas es más fiable que uno que arrasa en una sola.

**Por qué no se usa aquí.** Se midió. RRF es mucho más robusto frente a escalas
dispares, y de hecho **es el mejor sin reranker** para la consulta que nos
importaba (deja el Art. 12 en el puesto 4). Pero en el conjunto de evaluación baja
el nDCG@5 de **0.815 frente a 0.921**: al descartar la magnitud de los puntajes,
pierde precisión cuando la coincidencia léxica exacta sí importa. Con reranker
disponible, la fusión lineal es mejor en conjunto.

### 2.6 Reordenación con cross-encoder (*rerank*)

**Qué es.** Un **cross-encoder** —o *reranker*— es un modelo que recibe **la
consulta y el documento juntos** y devuelve una puntuación de cuánto responde ese
documento a esa pregunta. A diferencia del bi-encoder, que compara dos vectores
calculados por separado, aquí el modelo **lee los dos textos a la vez**, así que
puede captar la relación real entre ellos.

**Por qué no se usa para todo.** Es mucho más caro: hay que ejecutarlo una vez
**por cada par** (consulta, documento). Con 2 664 fragmentos sería inviable. Por
eso se usa como **segunda etapa**: la búsqueda híbrida recupera 30 candidatos y el
cross-encoder los reordena. Es el patrón habitual en recuperación: una etapa
barata que filtra y una cara que ordena.

**Qué resuelve.** El caso que originó todo el trabajo. El Art. 12 decía «quedan
autorizados para actuar como operadores cambiarios» y los formularios de la
Gerencia de Operaciones Cambiarias repiten «operador cambiario» muchas más veces.
BM25 premia la repetición y colocaba el artículo en el puesto 20; el cross-encoder
puntúa lo que **responde**, no lo que **coincide**, y lo sube al 3.º.

**Dónde se ejecuta.** El modelo pesa 2,2 GB y una función *serverless* de Vercel
admite 250 MB, así que en el portal desplegado se delega en un proveedor externo
por API. En local —y en un despliegue on-premise— se ejecuta el modelo
directamente.

### 2.7 Filtros por metadatos

Los filtros **restringen la búsqueda antes de puntuar**, usando los campos de
metadatos: tipo de norma (ley, decreto, resolución, convenio, circular), materia
(cambiario, general), entidades detectadas por NER y rango de fechas. Es la
diferencia entre «busca en todo» y «busca solo entre las resoluciones
cambiarias».

### 2.8 Degradación controlada

Cada pieza opcional tiene una salida: si no hay proveedor de *embeddings*, la
búsqueda usa **solo BM25**; si los vectores no corresponden al corpus, **también**;
si el reranker falla, se conserva **el orden de la búsqueda híbrida** y la
respuesta lo indica con `rerank: false`. Nada de esto interrumpe el servicio, y
nada de esto miente sobre lo que se hizo: informar de un rerank que no ocurrió es
peor que no informarlo.

---

## 3. Métricas de evaluación

### 3.1 Cómo se construye la verdad de referencia

Toda métrica necesita saber **qué documento es relevante** para cada consulta, y
eso normalmente exige anotación humana. Aquí se usó una aproximación automática:
se toma un fragmento del corpus, se **genera una consulta a partir de su propio
texto** y se considera relevante **el documento del que salió**. Es un conjunto
***silver*** —de plata, no de oro—: útil, reproducible y barato, pero con un sesgo
que se explica en §5.

La generación usa una **semilla fija (42)**, así que el mismo corpus produce
siempre las mismas consultas y todos los modelos se miden sobre exactamente lo
mismo.

### 3.2 recall@k (exhaustividad)

**Definición.** Proporción de documentos relevantes que aparecen entre los `k`
primeros resultados. `recall@5 = 0.9` significa que el 90 % de lo relevante está
en el top-5.

**En este sistema.** Como cada consulta tiene **un solo** documento relevante, el
recall@5 vale 1 si se encontró y 0 si no. Es, por tanto, una **tasa de acierto**:
la fracción de consultas cuyo documento aparece en el top-5.

**Para qué sirve aquí.** Es la métrica que responde a «¿lo encuentra o no lo
encuentra?». Lo primero que debe cumplir un buscador.

### 3.3 precision@k (precisión)

**Definición.** Proporción de los `k` resultados devueltos que son relevantes.
`precision@5 = 0.4` significa que 2 de los 5 son relevantes.

**En este sistema.** Con un único documento relevante, `precision@5` solo puede
valer 0.2 (encontrado) o 0 (no encontrado), así que **aporta poca información** y
no se usa para decidir. Se calcula por completitud. Sí tendría sentido con varios
documentos relevantes por consulta, que es lo deseable cuando exista un conjunto
de evaluación anotado por el BCV.

### 3.4 MRR (*Mean Reciprocal Rank*)

**Definición.** La media, sobre todas las consultas, del **inverso de la posición
del primer resultado relevante**. Si el relevante está 1.º, aporta 1; si está
2.º, 0.5; si está 3.º, 0.33; si no aparece, 0.

**Qué mide y por qué importa aquí.** No le importa *cuántos* relevantes se
recuperan, sino **cuán arriba está el primero**. Es exactamente lo que importa en
un asistente conversacional: los fragmentos que se envían al modelo de lenguaje
son los primeros, así que un documento relevante en el puesto 20 sirve de mucho
menos que uno en el puesto 2.

### 3.5 nDCG@k (*Normalized Discounted Cumulative Gain*)

Es la métrica principal del proyecto, y la más elaborada.

- **Ganancia (gain).** El valor de un resultado relevante. Aquí, 1 si lo es y 0 si
  no.
- **Descuento (discount).** Un acierto vale menos cuanto más abajo está. El
  descuento es logarítmico: `1 / log₂(posición + 1)`. El puesto 1 vale 1; el 2,
  0.63; el 3, 0.5; el 5, 0.39. La caída es rápida al principio y suave después,
  que es como se comporta la paciencia de un usuario.
- **DCG.** La suma de las ganancias descontadas. Es la calidad del ranking tal
  cual salió.
- **IDCG.** El DCG del **ranking ideal**: el mejor resultado posible. Es el techo
  contra el que comparar.
- **nDCG.** `DCG / IDCG`, normalizado entre 0 y 1 para que sea comparable entre
  consultas con distinto número de relevantes.

**En este sistema**, con un único relevante, `nDCG@5` se reduce a
`1 / log₂(posición + 1)` cuando se encuentra, y 0 cuando no. Es decir, **premia
acertar y además acertar arriba**, y por eso es la métrica que mejor refleja lo
que se quiere.

### 3.6 Latencia

**Definición.** El tiempo que tarda una consulta en devolver resultados. Importa
porque condiciona la arquitectura: es lo que descartó ejecutar el *reranker* en
una función *serverless*.

### 3.7 Métricas de operación

Complementan a las anteriores y en un despliegue real pesan tanto como ellas:

- **Tokens por consulta.** Consumo del proveedor externo. ~10 200 con 30
  candidatos.
- **Coste por mil consultas.** Traduce el consumo a dinero.
- **VRAM.** Memoria de GPU que ocupa cada modelo. Determina el hardware necesario.
- **Consultas por minuto.** Límite de tasa del proveedor. En el nivel gratuito de
  Jina, 100 000 tokens/minuto ≈ 9-10 consultas/minuto.

---

## 4. Resultados medidos

### 4.1 Corpus actual (2 664 fragmentos, 150 consultas)

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 (léxica) | 0.913 | 0.844 | 0.862 |
| Densa (e5-large) | 0.520 | 0.352 | 0.394 |
| **Híbrida α=0.5** | **0.940** | **0.865** | **0.884** |

### 4.2 Con reranker (40 consultas, mismo corpus)

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| Híbrida α=0.7, sin rerank | 0.975 | 0.902 | 0.921 |
| **Híbrida α=0.7 + rerank** | **0.975** | **0.910** | **0.926** |
| RRF α=0.5 (sin rerank) | 0.925 | 0.778 | 0.815 |

Se incluye RRF porque es la comparación que justifica la decisión: **gana en la
consulta concreta que preocupaba y pierde en el conjunto**.

### 4.3 Corpus anterior (2 083 fragmentos, 150 consultas)

Sirve para comparar modelos de *embeddings*. Se midió antes de ampliar el corpus.

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 | 0.933 | 0.835 | 0.860 |
| BGE-M3 densa | 0.773 | 0.618 | 0.657 |
| BGE-M3 híbrida | 0.953 | 0.855 | 0.879 |
| e5-large densa | 0.547 | 0.404 | 0.440 |
| e5-large híbrida | 0.947 | 0.853 | 0.877 |
| OpenAI `text-embedding-3-small` híbrida * | 0.875 | 0.803 | 0.820 |

\* medido sobre 40 consultas, no comparable directamente con las demás filas.

**Conclusiones:** la búsqueda densa *sola* es claramente peor que BM25 en un
corpus jurídico; la híbrida mejora a BM25 de forma modesta pero real; BGE-M3 y
e5-large empatan en la modalidad que se usa; y OpenAI no aporta nada que justifique
su coste.

### 4.4 Consultas reales: el caso del Art. 12

El conjunto *silver* no refleja las consultas humanas. Para cubrir eso se midió
algo distinto: **en qué puesto queda un artículo conocido** ante siete
formulaciones reales de la misma pregunta.

| Estrategia | Art. 12 en el top-5 |
|---|---:|
| BM25 | 2/7 |
| Densa | 4/7 |
| Híbrida α=0.5 | 3/7 |
| Híbrida α=0.7 | 5/7 |
| RRF α=0.5 | 6/7 |
| **Híbrida α=0.7 + rerank** | **7/7** |

La última fila está medida **sobre el portal desplegado**, con embeddings reales
y el *reranker* de Jina por API.

### 4.5 Latencia

| Operación | Tiempo |
|---|---:|
| Construir el índice BM25 (2 664 fragmentos) | 100-270 ms |
| Consulta BM25 | 1-4 ms |
| Búsqueda híbrida + rerank (desplegado) | **337-502 ms** |
| Rerank en CPU (30 candidatos) | ~16-22 s |
| Respuesta redactada por el modelo de lenguaje | 2-3 s adicionales |

La penúltima fila es la que decidió la arquitectura: 16 segundos por consulta en
CPU no caben en una función *serverless*, y por eso el *rerank* se delega en un
proveedor.

---

## 5. Qué mide bien el conjunto *silver*, y qué no

Esta es la lección metodológica más importante del proyecto y conviene dejarla
escrita.

El conjunto *silver* se construye **a partir del texto del propio documento**, así
que la consulta contiene palabras que están literalmente en el fragmento. Eso
**premia la coincidencia léxica exacta** y por tanto:

- **Favorece a BM25** por encima de lo que lo haría una consulta humana.
- **Esconde mejoras** que sí importan en la práctica. Ejemplo real: cuando se
  añadió la lematización por truncado, el agregado *silver* **bajó** de 0.860 a
  0.852; sin embargo, en la consulta real que había fallado, el artículo pasó del
  puesto 148 al 5. La métrica empeoró mientras el sistema mejoraba.
- **No distingue matices de orden** que un usuario sí nota.

Por eso el proyecto usa **las dos varas**: el conjunto *silver* para comparar
modelos entre sí con la misma vara, y **consultas reales** para comprobar que la
mejora llega al usuario.

### Error de muestreo

Con 150 consultas, las diferencias por debajo de **±0.028** de nDCG@5 no son
fiables: pueden ser ruido del conjunto y no señal. Con 40 consultas el margen es
mayor. Varias conclusiones del proyecto se corrigieron precisamente por esto —una
ventaja aparente de α=0.7 medida con 40 consultas desapareció al repetirla con
150.

---

## 6. Lo que se propuso y NO se implementó

Por honestidad, y porque son técnicas que un lector de la propuesta podría esperar
encontrar aquí:

| Técnica | Estado | Por qué |
|---|---|---|
| **HyDE** (*Hypothetical Document Embeddings*) | **No implementada** | Genera un documento hipotético con un modelo de lenguaje, lo vectoriza y busca con él. Añade una llamada de generación por consulta y su beneficio no está medido sobre este corpus |
| **Análisis de consultas** | **No implementado** | Clasificar la consulta (¿pide un artículo?, ¿un procedimiento?) para elegir estrategia. Requiere datos de uso reales que aún no existen |
| **Expansión de consultas** | **No implementada** | Añadir sinónimos o términos relacionados. La lematización por truncado cubre parte del problema con mucho menos coste |
| **Optimización de prompt** | **No implementada** | El *prompt* del asistente está redactado con cuidado, pero no se optimizó de forma sistemática contra un conjunto de respuestas de referencia |

No están porque **no se midieron y no se sabe si ayudan**. En este proyecto la
regla ha sido incorporar lo que se puede demostrar con números sobre el corpus
real; añadirlas sin medir habría sido exactamente lo contrario.

---

## 7. Cómo reproducir las mediciones

```bash
# Comparar modelos de embeddings sobre el corpus actual
python -m scripts.comparar_recuperacion \
  --conjunto "e5:web/api/_data/vectors.f32:web/api/_data/embeddings_meta.json" \
  --consultas 150

# Comparar cross-encoders de rerank
python -m scripts.comparar_rerankers --consultas 40 --candidatos 20

# Puesto de un artículo concreto ante varias formulaciones
python -m scripts.verificar_consulta \
  --patron "Quedan autorizados para actuar" \
  --consulta "requisitos para ser operador cambiario autorizado"

# Estado del despliegue y consumo del rerank
python -m scripts.verificar_despliegue https://<tu-app>.vercel.app
python -m scripts.verificar_despliegue --coste
```

---

## 8. Resumen en una tabla

| Técnica | Qué es | Estado | Efecto medido |
|---|---|---|---|
| BM25 | Recuperación léxica por coincidencia de palabras, con saturación y normalización por longitud | En uso | 0.862 de nDCG@5; 2/7 en consultas reales |
| Truncado a 7 caracteres | Lematización ligera que une plurales y géneros | En uso | Art. 12 del puesto 148 al 5 |
| Embeddings (e5-large) | Vector denso que representa el significado | En uso | Densa sola: 0.394 |
| Similitud coseno | Ángulo entre vectores, normalizados a longitud 1 | En uso | — |
| Índice HNSW | Grafo navegable de vecinos aproximados | En uso | Consultas en milisegundos |
| Fusión lineal | Suma ponderada de puntajes normalizados | En uso (α=0.7) | Híbrida: 0.884 |
| RRF | Fusión por posiciones, no por puntajes | **Descartada** | 0.815, pero 6/7 en consultas reales |
| Cross-encoder (rerank) | Modelo que lee consulta y documento juntos | En uso | 0.926 y **7/7** |
| Filtros por metadatos | Restricción previa por tipo, materia, entidades y fecha | En uso | — |
| NER con GLiNER | Detección de entidades sin entrenamiento específico | En uso | Alimenta los filtros |
| HyDE, análisis y expansión de consultas, optimización de prompt | — | **No implementadas** | Sin medir |

---

## 9. La conclusión que trasciende las métricas

Todas las cifras de este documento miden **cómo se ordena lo que hay**. El techo
real del sistema no está ahí.

La consulta que originó el proyecto —los requisitos para ser operador cambiario
autorizado— no fallaba por falta de precisión en la búsqueda, sino porque **la
norma que contiene esos requisitos no está en el corpus**. El Art. 12 solo dice
*quién* puede ser operador. Ninguna mejora de ranking, ningún modelo de
*embeddings* y ningún *reranker* pueden responder algo que no está en las fuentes.

Por eso la ampliación del corpus —**Gaceta Oficial y SUDEBAN**— es la única línea
de trabajo que cambia lo que el sistema *puede* responder. Las técnicas descritas
aquí garantizan que, cuando el fragmento exista, aparezca en el puesto correcto.
