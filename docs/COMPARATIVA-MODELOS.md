# Comparativa de modelos de embeddings

Medición **real** sobre el corpus jurídico del BCV (2 083 fragmentos). Todos los
modelos se miden con el **mismo** conjunto de consultas, derivado de forma
determinista del corpus (semilla fija), para que la comparación sea justa.

Reproducible con:

```bash
python -m scripts.comparar_recuperacion --k 5 --consultas 150 \
  --conjunto bge-m3:data/processed/vectores_bge-m3.f32:data/processed/vectores_bge-m3.meta.json \
  --conjunto e5:data/processed/vectores_e5.f32:data/processed/vectores_e5.meta.json
```

---

## 1. Resultado principal (150 consultas)

| Estrategia | recall@5 | MRR | nDCG@5 |
|---|---:|---:|---:|
| BM25 (léxico) | 0.933 | 0.835 | 0.860 |
| BGE-M3 · densa | 0.773 | 0.618 | 0.657 |
| **BGE-M3 · híbrida** (α=0.5) | **0.953** | **0.855** | **0.879** |
| e5-large · densa | 0.547 | 0.404 | 0.440 |
| e5-large · híbrida (α=0.5) | 0.947 | 0.853 | 0.877 |

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

Con 150 consultas: nDCG@5 pasa de **0.860 → 0.879** y recall@5 de **0.933 → 0.953**.
Es una mejora real, aunque modesta (~+0.02). Cuando la línea base léxica ya es
muy alta, el margen es estrecho.

### La búsqueda densa sola es claramente peor que BM25

0.657 (BGE-M3) y 0.440 (e5) frente a 0.860 de BM25. En un corpus jurídico los
términos exactos («Artículo 31», «encaje legal», siglas) pesan muchísimo.

> **Implicación práctica:** nunca actives solo la búsqueda semántica. Siempre
> híbrida, y con `alpha ≈ 0.5`, que es el valor por defecto del portal.

### BGE-M3 y e5-large están empatados en híbrida

**0.879 frente a 0.877.** La diferencia es ruido, no señal. Sí hay diferencia en
la parte densa (0.657 vs 0.440), pero al fusionar se diluye.

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
| **Sin cuentas nuevas** | **e5-large híbrida** | 0.877, con el token de HuggingFace que ya tienes |
| **Sin dependencias** | BM25 | 0.860, sin claves, sin coste, sin latencia extra |
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
términos diferentes:

| | antes | después |
|---|---:|---:|
| Art. 12 en BM25 | puesto **148** de 2 083 | puesto **5** |
| Art. 12 en híbrida | **fuera del top-10** | **4.º** |

El denso sí lo encontraba (puesto 4), pero la fusión lo arrastraba fuera porque
su puntaje léxico era bajísimo.

**Solución.** Recortar cada término a 7 caracteres, lo que une plurales y géneros
del español sin fusionar palabras distintas («autoridad» → `autorid`,
«autorizado» → `autoriz`). Verificado con cinco formulaciones distintas: el
artículo queda en el **top-5 en todas**.

**Efecto sobre el conjunto *silver*.** Las métricas agregadas bajan levemente:
BM25 0.860 → 0.852 y e5 híbrida 0.877 → 0.872. Es esperable y no invalida el
cambio: el conjunto *silver* se genera a partir del propio texto del corpus, así
que ya tiene coincidencia léxica exacta y **no puede reflejar** esta mejora. La
diferencia (−0.008) está dentro del error de muestreo de 150 consultas (±0.028),
mientras que la mejora en la consulta real es inequívoca.

**Lección metodológica:** un conjunto de evaluación derivado del corpus premia la
coincidencia exacta y puede esconder mejoras que sí importan en consultas
humanas. Conviene complementarlo con consultas reales.

**Se mantiene la lematización**, aplicada de forma idéntica en el buscador de
Vercel y en este comparador para que las mediciones sigan siendo comparables.

