# Comparación de motores de NER sobre el corpus del BCV

Este documento responde a una pregunta concreta: **¿qué motor de reconocimiento
de entidades conviene usar en este corpus, reglas o GLiNER?** La respuesta
habitual sería «GLiNER, es un modelo». Los datos dicen otra cosa, y son más
matizados de lo esperado.

Medición reproducible con `python -m scripts.comparar_ner --muestra 500`.

---

## 1. El problema de medir NER

Evaluar NER sin anotación humana es difícil porque «entidad correcta» es un
juicio. Para no depender de opiniones se usaron **tres pruebas objetivas**:

1. **Recall contra los metadatos del propio corpus.** Cada fragmento sabe de qué
   tipo de norma procede (`tipo_norma`), dato asignado en la ingesta y
   completamente ajeno al NER. Si un fragmento viene de una **Resolución**, un
   buen detector de `tipo_de_norma` debería encontrar la palabra «resolución» en
   su texto.
2. **Cobertura morfológica.** Formas que *deberían* detectarse, incluyendo
   plurales y variantes de género.
3. **Ruido en vocabulario cerrado.** Para las etiquetas cuya lista de valores
   válidos es finita, se listan los valores que cada motor produce **fuera** de
   esa lista, para poder juzgarlos uno a uno.

El **techo** es la pieza clave del método: de los fragmentos que vienen de una
Resolución, solo algunos contienen realmente la palabra. Nadie puede detectar lo
que no está escrito, así que el recall se mide **sobre los detectables**, no sobre
el total.

---

## 2. Recuperación de tipos de norma (la prueba decisiva)

| Tipo de norma | Fragmentos | Techo | Reglas | GLiNER |
|---|---:|---:|---:|---:|
| Resolución | 66 | 38 | **92 %** | 0 % |
| Circular | 30 | 19 | **100 %** | 0 % |
| Convenio cambiario | 43 | 26 | **69 %** | 0 % |
| Decreto | 20 | 16 | **100 %** | 0 % |
| Ley | 14 | 10 | **90 %** | 0 % |
| Aviso oficial | 27 | 11 | **82 %** | 0 % |

GLiNER detecta **cero** tipos de norma en unas 120 oportunidades reales.

Al principio se atribuyó a que la categoría «tipo de norma» no le funciona. El
apartado 8.3 muestra que la explicación es más matizada: en parte es que no la ve,
y en parte es que **la ve con una confianza tan baja que el umbral la descarta**.
En cualquier caso el resultado operativo es el mismo, y la conclusión —usar las
reglas para esta etiqueta— no cambia.

Las reglas, en cambio, alcanzan el techo en Circular y Decreto, y quedan cerca en
Resolución y Ley. La excepción es **Convenio cambiario** (69 %): muchos de esos
fragmentos citan el convenio como «el presente Convenio» sin repetir el tipo
completo.

---

## 3. Cobertura morfológica

**Cómo se lee esta tabla, porque es fácil equivocarse:**

- `n` = fragmentos **de la muestra** que contienen esa forma literal (búsqueda de
  texto, no una selección manual). Son cifras pequeñas porque la muestra es de
  500 sobre 2 664 fragmentos.
- El porcentaje = de esos `n`, en cuántos el motor produjo una entidad **de esa
  etiqueta**.

> ⚠️ **Ese porcentaje no significa «capturó esa forma»**, sino «ese fragmento
> acabó con una entidad de esa etiqueta, viniera de donde viniera». Para
> «operadores cambiarios» la diferencia es grande: de los 60 fragmentos del
> corpus que contienen ese plural, **26 (43 %) contienen además «mercado
> cambiario» u otra forma que sí casa**, y es esa la que dispara la regla. La
> medición estricta —¿se capturó *esta* forma?— está en el apartado **3b**, y ahí
> el plural da 0 % en todos los motores. **La conclusión práctica sale de 3b.**

Dicho eso, la tabla del apartado 3 responde a una pregunta que también importa:
¿el fragmento queda con una entidad de la etiqueta correcta? Eso es lo que
determina si un filtro lo encontrará.

| Forma esperada | Etiqueta | n | Reglas | GLiNER |
|---|---|---:|---:|---:|
| mercado cambiario | `materia_cambiaria` | 16 | **100 %** | 0 % |
| operadores cambiarios | `materia_cambiaria` | 31 | **58 %** | 0 % |
| casas de cambio | `materia_cambiaria` | 20 | **30 %** | 0 % |
| mesas de cambio | `materia_cambiaria` | 16 | 0 % | 0 % |
| resoluciones | `tipo_de_norma` | 20 | **60 %** | 0 % |
| circulares | `tipo_de_norma` | 23 | **22 %** | 0 % |
| leyes | `tipo_de_norma` | 42 | 0 % | 0 % |
| bolívares | `moneda` | 77 | **100 %** | 62 % |
| dólares | `moneda` | 31 | **100 %** | 65 % |
| euros | `moneda` | 19 | **100 %** | 84 % |
| transferencias | `sistema_de_pago` | 66 | **100 %** | 3 % |
| tipo de cambio | `indicador_economico` | 76 | **100 %** | 1 % |
| bancos universales | `institucion` | 34 | 0 % | **76 %** |

**Media ponderada: reglas 69 % · GLiNER 24 %.** Y en la comprobación **literal**
—exigiendo que el valor contenga la forma tal cual está escrita, no otra entidad
de la misma etiqueta— reglas 60 % frente a GLiNER 24 %.

Las reglas pierden por morfología: `ley` no captura `leyes`, `mesa de cambio` no
captura `mesas de cambio`. Ese es su punto débil real, y es el mismo problema que
en BM25 se resolvió truncando a 7 caracteres — aquí **no está resuelto**.

GLiNER gana en un solo caso: `bancos universales` (76 %), donde las reglas no
tienen ni una alternativa.

**Un hallazgo colateral:** la forma `mesa de cambio` **en singular no aparece en
ningún fragmento del corpus** (0 de 2 664). La expresión regular tiene esa
alternativa, pero nunca se ejecuta; solo existe el plural, «mesas de cambio» (23
fragmentos), que no se captura. Lo mismo ocurre con `\b(ley|…)\b`, cuyos topes de
palabra impiden casar `leyes`. La causa es la misma en ambos casos: **las reglas
no tienen morfología**. En BM25 ese problema se resolvió truncando a 7 caracteres;
aquí no está aplicado.

---

## 4. Dónde GLiNER sí aporta: vocabulario abierto

Al mirar los valores que GLiNER produce **fuera** del vocabulario de las reglas,
aparecen entidades que las reglas **pierden por completo** y que son relevantes:

| Etiqueta | Valores que solo detecta GLiNER | Veces |
|---|---|---:|
| `moneda` | moneda extranjera | 73 |
| | moneda nacional | 63 |
| | **divisas** | 22 |
| | monedas extranjeras | 21 |
| | us$ · m/e | 25 |
| `instrumento_financiero` | títulos valores | 30 |
| | tarjetas de crédito | 22 |
| | deuda pública nacional | 17 |
| | DPN | 15 |
| `sistema_de_pago` | sistemas de pago *(plural)* | 13 |
| | sistema nacional de pagos | 7 |
| | botones de pago | 5 |
| `institucion` | bancos universales | — |

**«Divisas» es un término central del BCV y las reglas no lo tienen.** Lo mismo
ocurre con «deuda pública nacional» o «títulos valores». Ahí GLiNER aporta valor
real y no sustituible por una lista escrita a mano, porque no se sabe de antemano
qué términos van a aparecer.

---

## 5. Dónde GLiNER mete ruido

El mismo mecanismo que le permite descubrir términos nuevos le hace producir
entidades **mal etiquetadas**. Los casos más frecuentes:

| Etiqueta | Valor | Veces | Juicio |
|---|---|---:|---|
| `sistema_de_pago` | sistema de mercado cambiario | 8 | **Incorrecto**: no es un sistema de pago |
| `sistema_de_pago` | mecanismo de intervención cambiaria | 6 | **Incorrecto** |
| `tipo_de_norma` | tipo de cambio | 1 | **Incorrecto**: es un indicador económico |
| `tipo_de_norma` | normativa · estándares internacionales | 7 | Discutible |
| `periodo` | plazo · mes · semana | 6 | **Incorrecto**: son duraciones, no períodos |
| `periodo` | 90 días · últimos tres (3) años | 3 | **Incorrecto** |
| `indicador_economico` | cobertura · plazo de pago | 4 | **Incorrecto** |

No es ruido marginal: en la prueba manual, «Sistema de Mercado Cambiario» recibió
`sistema_de_pago` con **0,806 de confianza**. Un filtro construido sobre eso
metería fragmentos equivocados con total seguridad.

---

## 6. Una hipótesis que resultó falsa

Se planteó que los nombres con guiones bajos (`sistema_de_pago`,
`materia_cambiaria`) perjudicaran a GLiNER, porque el modelo compara **el nombre
de la etiqueta como texto** contra el fragmento y `sistema_de_pago` no es
lenguaje natural. Se midió pasando las etiquetas en español normal:

| | GLiNER (guiones bajos) | GLiNER (lenguaje natural) |
|---|---:|---:|
| Cobertura | 92,6 % | 91,2 % |
| Entidades por fragmento | 4,3 | 4,1 |
| `tipo_de_norma` | 0 % | **0 %** |
| Cobertura morfológica | 24 % | 23 % |

**La hipótesis es falsa.** Los guiones bajos no eran el problema. Se deja
constancia porque el resultado negativo también es un resultado: ahorra que
alguien lo vuelva a intentar.

---

## 7. Conclusión: no gana ninguno, ganan por etiqueta

Los dos motores son buenos en cosas distintas y la evidencia dice exactamente en
cuáles:

| Etiqueta | Motor | Por qué |
|---|---|---|
| `tipo_de_norma` | **Reglas** | GLiNER: 0 % de detección |
| `indicador_economico` | **Reglas** | GLiNER: 1 %; «tipo de cambio» incluido |
| `periodo` | **Reglas** | GLiNER confunde duraciones con períodos |
| `materia_cambiaria` | **Reglas** | GLiNER: 0 % |
| `institucion` | **Unión** | GLiNER aporta «bancos universales» (76 %) |
| `moneda` | **Unión** | GLiNER aporta «divisas», «moneda extranjera» |
| `instrumento_financiero` | **Unión** | GLiNER aporta «títulos valores», «DPN» |
| `sistema_de_pago` | **Unión con revisión** | Aporta plurales; tiene un falso positivo conocido |

Esta combinación por etiqueta es la que se implementó en `src/ner.py`.

**Coste:** GLiNER tarda **566 ms por fragmento** (≈ 25 minutos para los 2 664 del
corpus en CPU). Las reglas, prácticamente cero. La combinación paga ese coste solo
en la fase de ingesta, que se ejecuta una vez.

---

## 8. Tres hallazgos posteriores que cambian el panorama

### 8.1 GLiNER solo lee los primeros 384 tokens

Durante la ejecución apareció este aviso, que no habíamos previsto:

```
UserWarning: Sentence of length 389 has been truncated to 384
```

No es un aviso menor. En `gliner/config.py` el parámetro `max_len` vale **384
tokens** por defecto, y nuestros fragmentos tienen una mediana de **1 791
caracteres, unos 447 tokens**:

| | |
|---|---:|
| Fragmentos analizados | 2 664 |
| Mediana de longitud | 1 791 caracteres (~447 tokens) |
| Límite de GLiNER | **384 tokens** (~1 536 caracteres) |
| **Fragmentos que lo superan** | **1 877 (70 %)** |

Es decir: en **siete de cada diez fragmentos, GLiNER no ve el final del texto**.
Las reglas leen el fragmento completo. Es una ventaja estructural de las reglas
en este corpus, donde los fragmentos son largos por diseño.

**Pero conviene ser preciso sobre qué explica y qué no.** El truncado **no**
explica el 0 % en `tipo_de_norma`: en la prueba manual, las palabras «decreto»,
«ley» y «resolución» estaban en los primeros 450 caracteres —dentro de la parte
visible— y GLiNER no detectó ninguna. Son dos limitaciones distintas y
acumulativas: una de alcance (el truncado) y otra de capacidad (la categoría).

### 8.2 Un defecto real: entidades partidas por saltos de línea

Al revisar la calidad de lo que había entrado apareció un problema que ninguna
de las tres pruebas anteriores detectaba, porque no afecta a *cuántas* entidades
se encuentran sino a *cómo se guardan*:

| Valor almacenado | Veces |
|---|---:|
| `institucion:banco central de venezuela` | 1 266 |
| `institucion:banco central de` + salto de línea + `venezuela` | 169 |
| `institucion:banco` + salto de línea + `central de venezuela` | 143 |

GLiNER devuelve el *span* tal cual aparece en el texto, y los documentos del BCV
traen saltos de línea en medio de los nombres. Como la normalización solo
recortaba los extremos, el salto quedaba dentro y **la misma entidad se guardaba
como tres valores distintos**.

La consecuencia es grave para un filtro: quien pidiera «fragmentos que mencionen
el Banco Central de Venezuela» obtendría 1 266 y **perdería 312 sin que nada lo
advirtiera**, porque para el sistema son entidades diferentes.

Se corrigió uniendo todos los espacios internos (`" ".join(v.split())`), lo que
fusionó **776 entradas duplicadas** sobre el total del corpus, y se añadió una
lista de falsos positivos medidos. Ambos cambios viven en
`src/ner.py::normalizar_entidades` y están cubiertos por pruebas.

### 8.3 La causa real del 0 %: el umbral, no (solo) la capacidad

Cerrando el cabo suelto anterior se midió la **puntuación** que GLiNER asigna a las
menciones, en vez de mirar solo si pasaban el umbral. Se consultó con
`threshold=0.05` para poder ver el valor.

`mesas de cambio`, en diez fragmentos reales que la contienen:

| Puntuación | ¿Pasa el umbral 0,4? |
|---:|---|
| 0,052 | no |
| 0,051 | no |
| 0,070 | no |
| 0,129 | no |
| *(sin detección)* | 6 de 10 |

`Resolución`, en doce fragmentos que la contienen:

| Puntuación | ¿Pasa el umbral 0,4? |
|---:|---|
| 0,072 · 0,054 · 0,064 · 0,051 · 0,076 · 0,118 | **ninguna** |
| *(sin detección)* | 8 de 12 |

**La conclusión es que el problema dominante no es que GLiNER no sepa, sino que
pierde confianza.** Con textos largos y etiquetas abstractas de dominio, sus
puntuaciones caen a 0,05-0,13, tres o cuatro veces por debajo del umbral de 0,4
—calibrado para entidades de propósito general, no para «tipo de norma» o
«materia cambiaria».

Conviene fijarse en que en la frase limpia y corta de la prueba manual GLiNER sí
daba 0,402 para «mesas de cambio»: **pasa el umbral por dos milésimas**. La misma
mención, dentro de un fragmento real de 1 800 caracteres, cae a 0,051.

**¿Y bajar el umbral?** No compensa, y se puede decir con datos: a 0,05 GLiNER
recupera 4 de 12 «Resolución» frente al 92 % de las reglas, y para lograrlo
empieza a producir spans incorrectos como *«Los reportes generados por las mes»*
(0,052). Se cambiaría un problema de cobertura por uno de precisión.

Esto refuerza la decisión de la combinación por etiqueta en vez de debilitarla.

---

## 9. Resultado final sobre el corpus

Ejecutado sobre los 2 731 fragmentos, con la combinación por etiqueta:

| | Antes (solo reglas) | Ahora (combinado) |
|---|---:|---:|
| Fragmentos con entidades | 2 445 (89,5 %) | **2 678 (98,1 %)** |
| Entidades totales | 11 681 | 18 987 |

Y por etiqueta, que es donde se ve el diseño:

| Etiqueta | Antes | Ahora | Cambio |
|---|---:|---:|---:|
| `tipo_de_norma` | 1 474 | 1 474 | **0 %** |
| `periodo` | 5 053 | 5 053 | **0 %** |
| `indicador_economico` | 373 | 373 | **0 %** |
| `materia_cambiaria` | 173 | 173 | **0 %** |
| `institucion` | 2 062 | 6 255 | +203 % |
| `moneda` | 907 | 2 261 | +149 % |
| `instrumento_financiero` | 292 | 1 965 | +573 % |
| `sistema_de_pago` | 1 347 | 2 209 | +64 % |

Las cuatro primeras **no cambian ni una unidad**: son las de reglas, y que sigan
exactamente iguales demuestra que GLiNER no metió ruido en ellas. Las cuatro
últimas crecen porque GLiNER sí aporta ahí, con términos que las reglas no tienen
(«divisas», «títulos valores», «deuda pública nacional», «bancos universales»).

**No hizo falta re-vectorizar.** El número de fragmentos sigue siendo 2 664 —el
filtro de exportación depende de la longitud del texto, no de las entidades— así
que los vectores actuales siguen alineados. Solo hubo que re-exportar
`corpus.json`.

---

## 10. La advertencia que importa más que el resultado

Todo este trabajo mejora los **metadatos** de cada fragmento. Pero conviene
comprobar dónde se usan, porque de eso depende que sirva para algo.

Hoy, en el portal desplegado, los filtros disponibles son **solo `materia` y
`tipo_norma`**:

```js
if (f.materia) out.materia = String(f.materia);
if (f.tipo_norma) out.tipo_norma = String(f.tipo_norma);
```

Las entidades viajan en los resultados y se muestran en las citas, pero **no se
puede pedir «solo fragmentos que mencionen SUDEBAN»**. En el backend Python sí
existe ese filtro (sobre Weaviate), así que la capacidad está construida y sin
usar en el Modo A.

**Consecuencia práctica:** mejorar el NER no cambia nada visible para el usuario
hasta que se conecte el filtro por entidades. Es trabajo de valor real, pero su
rendimiento está pendiente de dos cosas: esa conexión y las fuentes que faltan
(Gaceta Oficial, SUDEBAN).

---

## 11. Cómo reproducirlo

```bash
python -m scripts.comparar_ner --muestra 500
```

Genera las cinco tablas de este documento y escribe
`data/processed/informe_ner.json`.
