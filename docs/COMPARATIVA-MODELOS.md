# Comparativa de modelos de embeddings

Medición **real** sobre el corpus jurídico del BCV. Todos los modelos se miden
con el **mismo** conjunto de consultas, derivado de forma determinista del corpus
(semilla fija), para que la comparación sea justa.

> El corpus pasó de **2 083** a **2 664** fragmentos al incorporar las secciones
> de actos administrativos (§6). Las filas de **e5-large** y **BM25** están
> medidas sobre el corpus actual; las de **BGE-M3** siguen siendo las de la
> medición anterior (2 083 fragmentos), porque no se volvió a vectorizar con ese
> modelo. La comparación entre familias es orientativa, no exacta.

Reproducible con:

```bash
python -m scripts.comparar_recuperacion --k 5 --consultas 150 \
  --conjunto bge-m3:data/processed/vectores_bge-m3.f32:data/processed/vectores_bge-m3.meta.json \
  --conjunto e5:web/api/_data/vectors.f32:web/api/_data/embeddings_meta.json
```

---

## 1. Resultado principal (150 consultas)

Corpus actual, **2 664 fragmentos**:

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 (léxico) | 0.913 | 0.844 | 0.862 |
| e5-large · densa | 0.520 | 0.352 | 0.394 |
| **e5-large · híbrida** (α=0.5) | **0.940** | **0.865** | **0.884** |

Corpus anterior, 2 083 fragmentos (referencia):

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 (léxico) | 0.933 | 0.835 | 0.860 |
| BGE-M3 · densa | 0.773 | 0.618 | 0.657 |
| BGE-M3 · híbrida (α=0.5) | 0.953 | 0.855 | 0.879 |
| e5-large · densa | 0.547 | 0.404 | 0.440 |
| e5-large · híbrida (α=0.5) | 0.947 | 0.853 | 0.877 |

La ampliación del corpus **no degradó** la línea base: BM25 pasó de 0.860 a
0.862 y e5 híbrida de 0.877 a 0.884.

---

## 2. OpenAI `text-embedding-3-small` (40 consultas)

Se midió desde Colab, con un conjunto de 40 consultas (no 150), así que sus
valores **no** son directamente comparables a la tabla anterior. Lo que sí es
válido es compararlo **dentro de su propio conjunto**:

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 (léxico) | 0.900 | 0.796 | 0.821 |
| OpenAI · densa | 0.650 | 0.592 | 0.607 |
| OpenAI · híbrida (α=0.5) | 0.875 | 0.803 | 0.820 |

**En el mismo conjunto de 40 consultas:** BM25 daba 0.821 y OpenAI híbrida 0.820.
Es decir, **OpenAI no aportó ninguna mejora** — de hecho bajó el recall (0.900 →
0.875), porque la fusión arrastró el ranking hacia un componente denso más débil.

---

## 3. Conclusiones

### La búsqueda híbrida mejora a BM25, pero poco

Con 150 consultas sobre el corpus actual: nDCG@5 pasa de **0.862 → 0.884** y
recall@5 de **0.913 → 0.940**. Es una mejora real, aunque modesta (~+0.02).
Cuando la línea base léxica ya es muy alta, el margen es estrecho.

### La búsqueda densa sola es claramente peor que BM25

0.657 (BGE-M3) y 0.394 (e5) frente a 0.862 de BM25. En un corpus jurídico los
términos exactos («Artículo 31», «encaje legal», siglas) pesan muchísimo.

> **Implicación práctica:** nunca actives solo la búsqueda semántica. Siempre
> híbrida, y con `alpha ≈ 0.5`, que es el valor por defecto del portal.

### BGE-M3 y e5-large están empatados en híbrida

**0.879 frente a 0.877** (medición sobre 2 083 fragmentos). La diferencia es
ruido, no señal. Sí hay diferencia en la parte densa (0.657 vs 0.440), pero al
fusionar se diluye.

### El `alpha` importa menos de lo que parecía

Barrido con 40 consultas:

| alpha | BGE-M3 híbrida | e5 híbrida |
|---|---:|---:|
| 0.3 | 0.874 | 0.854 |
| 0.5 | 0.881 | 0.852 |
| 0.7 | 0.836 | 0.892 |

e5 parecía ganar con α=0.7 (**0.892**), pero al repetir con 150 consultas
α=0.5 dio **0.877** y α=0.7 dio **0.874**. **La ventaja era ruido del conjunto
pequeño.** Con 40 consultas, diferencias por debajo de ~0.03 no son fiables.

### OpenAI no aporta en este corpus

Quedó al nivel de BM25 en su propio conjunto y por debajo de BGE-M3 y e5. No
justifica su coste aquí.

---

## 4. Recomendación

| Objetivo | Elección | Motivo |
|---|---|---|
| **Máximo rendimiento** | BGE-M3 híbrida | 0.879, el mejor (empate técnico con e5) |
| **Sin cuentas nuevas** | **e5-large híbrida** | 0.884 en el corpus actual, con el token de HuggingFace que ya tienes |
| **Sin dependencias** | BM25 | 0.862, sin claves, sin coste, sin latencia extra |
| **OpenAI** | ❌ No usarlo | 0.820: no mejora a BM25 y cuesta dinero |

**En la práctica: quédate con e5-large.** Empata con BGE-M3 en la modalidad que
se usa de verdad (híbrida) y funciona con el token que ya tienes, sin crear
cuentas ni pagar. BGE-M3 solo se justifica si en el futuro se quiere usar la
búsqueda densa sola, donde sí es bastante mejor (0.657 vs 0.440).

En cualquier caso el portal **cae a BM25 automáticamente** si el proveedor falla,
así que activar los embeddings no añade riesgo.

---

## 5. Lematización ligera del buscador léxico

Una consulta **real** de un usuario falló:

> «¿Qué requisitos exige el BCV para ser operador cambiario autorizado?»
> → el asistente respondió que el contexto no contenía la información.

Y sí la contenía: el **Artículo 12** dice «quedan autorizados para actuar como
operadores cambiarios».

**Causa.** La consulta usa *operador · cambiario · autorizado* y el artículo dice
*operadores · cambiarios · autorizados*. Sin lematización, BM25 los trata como
términos diferentes: el Art. 12 caía al puesto **148** y la fusión lo dejaba
fuera del top-10.

El denso sí lo encontraba (puesto 4), pero la fusión lo arrastraba fuera porque
su puntaje léxico era bajísimo.

**Solución.** Recortar cada término a 7 caracteres, lo que une plurales y géneros
del español sin fusionar palabras distintas («autoridad» → `autorid`,
«autorizado» → `autoriz`).

**Efecto sobre el conjunto *silver*.** Las métricas agregadas bajaron levemente en
su momento: BM25 0.860 → 0.852 y e5 híbrida 0.877 → 0.872. Es esperable y no
invalida el cambio: el conjunto *silver* se genera a partir del propio texto del
corpus, así que ya tiene coincidencia léxica exacta y **no puede reflejar** esta
mejora. La diferencia (−0.008) está dentro del error de muestreo de 150 consultas
(±0.028), mientras que la mejora en la consulta real es inequívoca.

**Lección metodológica:** un conjunto de evaluación derivado del corpus premia la
coincidencia exacta y puede esconder mejoras que sí importan en consultas
humanas. Conviene complementarlo con consultas reales.

**Se mantiene la lematización**, aplicada de forma idéntica en el buscador de
Vercel y en este comparador para que las mediciones sigan siendo comparables.
Para comprobar el puesto de un fragmento concreto ante varias formulaciones:

```bash
python -m scripts.verificar_consulta \
  --patron "Quedan autorizados para actuar" \
  --consulta "requisitos para ser operador cambiario autorizado"
```

---

## 6. Regresión conocida: el Art. 12 tras ampliar el corpus

La ampliación con las secciones de actos administrativos incorporó **563
fragmentos nuevos**, muchos de ellos formularios e instructivos de la Gerencia de
Operaciones Cambiarias que repiten «operador cambiario» muchas veces. Eso mejora
la cobertura, pero **compite** por las consultas de esa familia.

Puesto del **Art. 12** (Convenio Cambiario N.º 1) sobre 2 664 fragmentos:

| Consulta | BM25 | Densa | Híbrida (α=0.5) |
|---|---:|---:|---:|
| «autorización para actuar como operador cambiario» | 1 | 4 | **1** |
| «quién puede actuar como operador cambiario en Venezuela» | 1 | 2 | **1** |
| «requisitos para operar como operador cambiario» | 8 | 25 | **5** |
| «qué se necesita para ser banco operador cambiario autorizado» | 20 | 8 | 10 |
| «quiénes pueden ser operadores cambiarios» | 31 | 4 | 12 |

Con 2 083 fragmentos el artículo quedaba en el top-5 en las cinco
formulaciones; ahora queda en **dos de cinco**, y las que fallan son las
**cortas y naturales** — precisamente las que escribe un usuario.

### Dos causas distintas, no una

1. **Ruido de ranking.** Los formularios ganan por repetición de términos y
   desplazan al artículo.
2. **Cobertura.** El corpus **no contiene** la norma que fija los requisitos para
   ser operador cambiario: el Art. 12 solo dice *quién* puede serlo (los bancos
   universales) y remite a autorizaciones conjuntas del Ministerio de Finanzas y
   del BCV. Faltan las fuentes donde están esos requisitos (Gaceta Oficial,
   SUDEBAN). Ningún ajuste de ranking puede responder algo que no está en el
   corpus.

**Comprobado:** de los 563 fragmentos nuevos, 142 mencionan «operador cambiario»
y **ninguno** menciona requisitos de autorización.

### Se probaron estrategias de fusión alternativas

Barrido sobre el corpus actual. La columna «Art. 12 en top-5» cuenta en cuántas
de las siete formulaciones reales de la tabla anterior el artículo entra al
top-5:

| Estrategia de fusión | nDCG@5 *silver* | Art. 12 en top-5 |
|---|---:|---:|
| BM25 (sin fusión) | 0.861 | 2/7 |
| densa (sin fusión) | 0.394 | 4/7 |
| **lineal α=0.5 (la actual)** | **0.884** | **3/7** |
| lineal α=0.7 | 0.882 | 5/7 |
| RRF (k=60, α=0.5) | 0.771 | 6/7 |
| lineal + RRF (0.3/0.7) | 0.875 | 5/7 |
| lineal + RRF (0.5/0.5) | 0.862 | 5/7 |

Dos lecturas:

- **El conjunto *silver* y las consultas humanas miden cosas distintas.** RRF es
  el mejor para las consultas reales (6/7) y el peor en *silver* (0.771), porque
  el conjunto *silver* se construye con el texto del propio documento y premia la
  coincidencia léxica exacta, justo lo que RRF descarta al ignorar la magnitud de
  los puntajes.
- **Ninguna fusión por sí sola resuelve la consulta original.** Su mejor puesto
  es 4.º con RRF α=0.5, pero a costa de 0.11 de nDCG@5. Subir α a 0.7 es el
  cambio más barato (una constante) y lleva las formulaciones acertadas de 3/7 a
  5/7 con una pérdida de 0.002.

**La solución de fondo es un *rerank* con cross-encoder** sobre la unión de
candidatos: el Art. 12 está en el top-5 denso y en el top-35 léxico, así que un
reranker que lea consulta y fragmento juntos lo puntuaría por su contenido real y
no por cuántas veces repite una palabra. El modelo `BAAI/bge-reranker-v2-m3` ya
está en la caché local y es el que contempla la propuesta técnica, pero **no cabe
en una función serverless de Vercel**: exige el Modo B (backend dedicado) o un
proveedor de *rerank* por API.

