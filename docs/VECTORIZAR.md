# Vectorizar el corpus con OpenAI (guía paso a paso)

Esta guía genera los **vectores del corpus jurídico** para activar la búsqueda
semántica en el portal desplegado en Vercel. Se ejecuta **una sola vez** (y de
nuevo solo si cambia el corpus).

---

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
