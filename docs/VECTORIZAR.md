# Vectorizar el corpus (guía paso a paso)

Esta guía genera los **vectores del corpus jurídico** para activar la búsqueda
semántica en el portal desplegado en Vercel. Se ejecuta **una sola vez** (y de
nuevo solo si cambia el corpus).

---

## 0. Vía recomendada: reutilizar los vectores locales (sin API, sin costo)

El pipeline local **ya calculó** los vectores con BGE-M3 al indexar en Weaviate.
En lugar de volver a vectorizar por API (lo que además choca con los bloqueos
geográficos de algunos proveedores), basta con alinearlos con el corpus:

```bash
python -m scripts.export_vectors_local
```

Lee `space/data/objects.jsonl` + `space/data/vectors.npy` y escribe
`web/api/_data/vectors.f32` (2 083 × 1 024, L2-normalizado) y su meta.

**Ventajas:** costo cero, sin claves, sin restricciones de país y sin volver a
ejecutar el modelo. El emparejamiento es por texto exacto, así que si algún
fragmento no encontrara su vector el script lo avisa y se detiene.

Con esto, **el corpus está listo**. Lo único que necesita un proveedor externo
es la **consulta** en tiempo de ejecución (la función de Vercel no puede correr
BGE-M3), y ese proveedor debe servir **el mismo modelo**: `BAAI/bge-m3`.

### Si no consigues proveedor de embeddings

No pasa nada: el portal funciona igual con BM25, que en la evaluación del corpus
fue **la estrategia con mejor nDCG@5 (0.863)**. La búsqueda semántica es una
mejora, no un requisito.

---

## Vía alternativa: vectorizar por API

Úsala solo si prefieres otro modelo (por ejemplo, uno de OpenAI) o si el corpus
cambia y quieres regenerarlo con un proveedor externo.

### Desde Google Colab (recomendado si el proveedor bloquea tu país)

OpenAI bloquea por región (`unsupported_country_region_territory`). Colab sale a
internet desde regiones admitidas, así que sirve como puente.

**Cuaderno listo:** [`notebooks/vectorizar_openai_colab.ipynb`](../notebooks/vectorizar_openai_colab.ipynb)

[![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/uptaragua-oficial/bcv-conocimiento-vectorial/blob/main/notebooks/vectorizar_openai_colab.ipynb)

Hace todo en cuatro pasos: clona el repositorio (es público), pide la clave con
`getpass` (no queda visible en la salida), vectoriza y descarga los dos archivos.
Incluye una celda que muestra los fragmentos más cercanos a una consulta, útil
para **comparar la calidad entre modelos**.

Al terminar, copia `vectors.f32` y `embeddings_meta.json` a `web/api/_data/`,
haz commit y configura en Vercel `EMBEDDINGS_API_KEY` y `EMBEDDINGS_MODEL` con el
mismo modelo que usaste.

> ⚠️ Los vectores y la meta deben ser **del mismo modelo**. Si cambias uno y no
> el otro, el sistema detecta el desajuste y vuelve a BM25 (con un aviso en
> consola), en lugar de devolver resultados incorrectos.

### Desde tu máquina


## 1. Entender qué pasa y por qué

Hay dos momentos distintos, y conviene no confundirlos:

| Momento | Qué ocurre | Dónde |
|---|---|---|
| **Ahora (una vez)** | Cada fragmento del corpus se convierte en un vector de números. El resultado se guarda en un archivo | Tu máquina |
| **Cada consulta** | Solo la pregunta del usuario se convierte en vector, y se compara con los ya guardados | Función serverless de Vercel |

El modelo debe ser **el mismo** en ambos lados: si vectorizas con
`text-embedding-3-small` y en Vercel configuras otro, los vectores no serían
comparables. El sistema lo detecta y vuelve a BM25 automáticamente en lugar de
dar resultados incorrectos.

**Costo:** ~2 000 fragmentos ≈ 1 millón de tokens ≈ **unos pocos céntimos**.

---

## 2. Requisitos

- Python 3.10 o superior. **No hace falta instalar nada**: el script usa solo la
  biblioteca estándar.
- Una clave de OpenAI (<https://platform.openai.com/api-keys>).
- Haber generado antes el corpus:

  ```bash
  python -m scripts.export_vercel_index     # crea web/api/_data/corpus.json
  ```

  Si ya existe `web/api/_data/corpus.json`, puedes saltar este paso.

---

## 3. Ejecutar

Desde la raíz del repositorio:

```bash
export EMBEDDINGS_API_KEY=sk-...      # tu clave de OpenAI
python -m scripts.export_openai_embeddings
```

Verás el progreso por lotes y, al terminar, algo así:

```
Vectorizando 2083 fragmentos con text-embedding-3-small (https://api.openai.com/v1/embeddings)
  256/2083
  ...
  2083/2083

OK · 2083 vectores de 1536 dims → web/api/_data/vectors.f32 (12.8 MB)
Meta → web/api/_data/embeddings_meta.json
```

### Qué se ha creado

| Archivo | Contenido |
|---|---|
| `web/api/_data/vectors.f32` | Matriz de vectores en binario (Float32), ya normalizada |
| `web/api/_data/embeddings_meta.json` | Modelo, dimensiones y número de vectores |

> El orden de los vectores coincide **exactamente** con el de los fragmentos de
> `corpus.json`. Eso es lo que garantiza que al buscar se señale el artículo
> correcto. No edites ninguno de los dos archivos por separado.

---

## 4. Verificar antes de subir

```bash
cat web/api/_data/embeddings_meta.json
```

Debe indicar el modelo que usaste y `"n": 2083`. Puedes probar la búsqueda
híbrida en local con el emulador de Vercel y el modelo simulado:

```bash
cd web
npm run mock:embeddings        # en otra terminal
# y en una tercera, con las variables apuntando al simulador…
```

---

## 5. Publicar y activar en Vercel

```bash
git add web/api/_data/vectors.f32 web/api/_data/embeddings_meta.json
git commit -m "chore: vectorizar el corpus con text-embedding-3-small"
git push
```

En Vercel → **Settings → Environment Variables**:

| Variable | Valor |
|---|---|
| `EMBEDDINGS_API_KEY` | tu clave de OpenAI |
| `EMBEDDINGS_MODEL` | `text-embedding-3-small` *(el mismo de la meta)* |
| `DEEPSEEK_API_KEY` | tu clave de DeepSeek, para las respuestas redactadas |

**Redespliega** (Vercel lo hace solo al hacer push si ya está conectado) y
comprueba:

```bash
curl https://<tu-app>.vercel.app/api/health
```

Debe responder `"recuperacion": "hibrida"` y `"motor": "hibrido"`. En el portal,
la cabecera mostrará la etiqueta **«Búsqueda híbrida»**.

---

## 6. Si algo falla

| Síntoma | Causa probable |
|---|---|
| `Falta EMBEDDINGS_API_KEY` | No exportaste la variable en esa terminal |
| `Error HTTP 401` | La clave no es válida o está revocada |
| `Error HTTP 404` | El modelo no existe o tu cuenta no tiene acceso |
| `/api/health` sigue en `keyword` | Falta la variable en Vercel, no se redesplegó, o el modelo configurado no coincide con el de `embeddings_meta.json` |
| Los resultados empeoran | Prueba otro `alpha` (0 = solo BM25, 1 = solo semántico) |

---

## 7. Preguntas frecuentes

**¿Y si cambio de proveedor de embeddings?**
Cambia `EMBEDDINGS_BASE_URL` y `EMBEDDINGS_MODEL`, vuelve a vectorizar y
reconfigura. El formato es el de OpenAI, así que sirven DeepInfra, Jina, Voyage…
DeepInfra, por ejemplo, sirve `BAAI/bge-m3`, el mismo modelo del backend Python.

**¿Puedo usar un modelo más preciso?**
Sí: `EMBEDDINGS_MODEL=text-embedding-3-large` (3 072 dimensiones, ~26 MB de
vectores). Recuerda usarlo también en Vercel.

**¿Cuándo hay que repetirlo?**
Solo si cambia el corpus (nuevas normas) o si cambias de modelo. Al
re-vectorizar, el script reescribe ambos archivos completos.
