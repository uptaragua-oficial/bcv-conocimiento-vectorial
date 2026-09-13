# Vectorizar el corpus (guía paso a paso)

Esta guía genera los **vectores del corpus jurídico** que activan la búsqueda
semántica en el portal desplegado en Vercel. Se ejecuta **una sola vez**, y de
nuevo solo si cambia el corpus o si cambias de modelo.

Hay dos momentos que conviene no confundir:

| Momento | Qué ocurre | Dónde |
|---|---|---|
| **Una vez, ahora** | Cada fragmento del corpus se convierte en un vector. El resultado se guarda en un archivo que viaja con el repositorio | Tu máquina |
| **Cada consulta** | Solo la pregunta del usuario se convierte en vector, y se compara con los ya guardados | Función serverless de Vercel |

El modelo debe ser **el mismo** en ambos lados. Si no coincide, el sistema lo
detecta y vuelve a BM25 automáticamente, en lugar de devolver resultados
incorrectos.

---

## 1. Vía recomendada: calcular los vectores en local

**No necesita ninguna clave de API.** El proveedor externo solo hace falta
después, en tiempo de ejecución, y únicamente para vectorizar la consulta.

```bash
export HF_HOME=/ruta/a/tu/cache/huggingface      # reutiliza el modelo ya descargado
export PYTHONPATH=.pylibs:.                      # dependencias del proyecto
python -m scripts.export_embeddings_local
```

Escribe `web/api/_data/vectors.f32` y `embeddings_meta.json`. El modelo por
defecto es `intfloat/multilingual-e5-large` (1 024 dimensiones), que fue el de
mejor desempeño en la comparativa (§4).

### La GPU es opcional

El script usa la GPU **si la encuentra** y, si no, sigue en CPU sin cambiar
nada del resultado: el modelo y los vectores son idénticos. Para forzar el
dispositivo:

```bash
EMBED_DEVICE=cpu  python -m scripts.export_embeddings_local
EMBED_DEVICE=cuda python -m scripts.export_embeddings_local
```

| Dispositivo | 2 664 fragmentos |
|---|---|
| GPU (RTX 3060 Ti) | ~1 minuto (estimado) |
| CPU (20 núcleos) | ~30 minutos (medido) |

Una compilación **CUDA** de PyTorch es un requisito de la GPU, no del script:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# 2.14.0+cpu False   → instalación solo-CPU (correcto si vas a usar CPU)
# 2.14.0+cu128 True  → GPU disponible
```

> Ojo con las instalaciones interrumpidas: si `pip` se corta a mitad, puede
> quedar el `.dist-info` de la versión CUDA pero el paquete `torch/` de la
> versión CPU. Se detecta porque falta `torch/lib/libtorch_cuda.so`. En ese caso,
> reinstala con `--force-reinstall`.

### Es reanudable

El avance se guarda **lote a lote** con `fsync` en
`data/processed/embeddings_avance.json`. Un corte de luz, un reinicio o un
`Ctrl-C` solo cuestan el último lote: al volver a ejecutar el mismo comando
continúa donde quedó. Para empezar de cero:

```bash
python -m scripts.export_embeddings_local --reiniciar
```

### Variables

| Variable | Por defecto | Para qué |
|---|---|---|
| `EMBED_MODEL` | `intfloat/multilingual-e5-large` | Modelo a usar |
| `EMBED_PREFIJO_DOC` | `passage: ` | Prefijo de los documentos |
| `EMBED_PREFIJO_Q` | `query: ` | Prefijo de las consultas |
| `EMBED_FORMATO` | `huggingface` | Formato del proveedor en ejecución |
| `EMBED_LOTE` | `16` | Tamaño de lote |
| `EMBED_DEVICE` | automático | `cpu`, `cuda` o `mps` |

---

## 2. Vía alternativa: reutilizar los vectores de BGE-M3

Si ya indexaste en Weaviate, esos vectores existen y se pueden reaprovechar sin
volver a ejecutar el modelo. Empareja por **texto exacto**, así que si algún
fragmento no encontrara su vector el script lo avisa y se detiene:

```bash
python -m scripts.export_vectors_local
```

Requiere un proveedor que sirva `BAAI/bge-m3` **como embeddings** (por ejemplo
DeepInfra; el router de Hugging Face solo lo ofrece como similitud de frases).
En la comparativa, BGE-M3 híbrido y e5 híbrido quedaron prácticamente empatados
(0.879 frente a 0.877), por lo que la vía local de §1 evita abrir otra cuenta sin
perder calidad.

---

## 3. Vía alternativa: vectorizar por API

Úsala solo si prefieres otro modelo (por ejemplo, uno de OpenAI).

### Desde Google Colab (recomendado si el proveedor bloquea tu país)

OpenAI bloquea por región (`unsupported_country_region_territory`). Colab sale a
internet desde regiones admitidas, así que sirve como puente.

**Cuaderno listo:** [`notebooks/vectorizar_openai_colab.ipynb`](../notebooks/vectorizar_openai_colab.ipynb)

[![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/uptaragua-oficial/bcv-conocimiento-vectorial/blob/main/notebooks/vectorizar_openai_colab.ipynb)

Clona el repositorio (es público), pide la clave con `getpass` (no queda visible
en la salida), vectoriza, muestra los fragmentos más cercanos a una consulta y
descarga los dos archivos.

### Desde tu máquina

El script de API usa **solo la biblioteca estándar**, así que no hay nada que
instalar. Necesitas Python 3.10 o superior, una clave de OpenAI y el corpus ya
generado:

```bash
python -m scripts.export_vercel_index     # crea web/api/_data/corpus.json
export EMBEDDINGS_API_KEY=sk-...
python -m scripts.export_openai_embeddings
```

**Costo:** ~2 700 fragmentos ≈ 1,5 millones de tokens ≈ unos pocos céntimos.

---

## 4. Qué modelo elegir

Evaluación sobre 150 consultas, midiendo **nDCG@5** (más alto es mejor):

| Estrategia | nDCG@5 |
|---|---|
| BGE-M3 híbrida | 0.879 |
| e5-large híbrida | 0.877 |
| BM25 (solo palabras clave) | 0.860 |
| BGE-M3 densa | 0.657 |
| e5-large densa | 0.440 |

Conclusiones:

- La **fusión híbrida** supera a BM25 en las dos familias. La ganancia es real
  pero moderada: BM25 solo ya es un buen motor.
- La búsqueda **densa sola** es claramente peor. Nunca conviene usarla sin BM25.
- **OpenAI `text-embedding-3-small` quedó descartado**: híbrida 0.820 frente a
  0.860 de BM25 sobre el mismo subconjunto, y además exige resolver el bloqueo
  geográfico. No compensa su costo.

Puedes reproducir la tabla con:

```bash
python -m scripts.comparar_recuperacion \
  --conjunto "e5:data/processed/vectores_e5.f32:data/processed/vectores_e5.meta.json" \
  --consultas 150
```

---

## 5. Verificar antes de subir

```bash
cat web/api/_data/embeddings_meta.json
```

`"n"` debe coincidir con el número de fragmentos de `corpus.json`, y el tamaño
de `vectors.f32` debe ser exactamente `n × dim × 4` bytes. Un vector
desalineado es peor que no tener vectores, así que el portal lo comprueba: si
`n` no cuadra, `/api/health` responde `"recuperacion": "keyword"` y
`"vectores": {"alineados": false}` en lugar de arriesgar resultados incorrectos.

Para probar la búsqueda híbrida en local está el emulador de Vercel y un
servidor de embeddings simulado:

```bash
cd web
npm run mock:embeddings
npm run dev:vercel
```

---

## 6. Publicar y activar en Vercel

```bash
git add web/api/_data/vectors.f32 web/api/_data/embeddings_meta.json
git commit -m "chore: vectorizar el corpus ampliado con multilingual-e5-large"
git push
```

En Vercel → **Settings → Environment Variables**:

| Variable | Valor |
|---|---|
| `EMBEDDINGS_API_KEY` | tu token de Hugging Face, con el prefijo `hf_` |
| `DEEPSEEK_API_KEY` | tu clave de DeepSeek, con el prefijo `sk-` |

El modelo, la URL y el prefijo de consulta **no** se configuran a mano: se leen
de `embeddings_meta.json`, de modo que la función de Vercel se configura sola.

**Redespliega** (Vercel lo hace solo al hacer push si ya está conectado) y
comprueba:

```bash
curl https://<tu-app>.vercel.app/api/health
```

Debe responder `"recuperacion": "hibrida"`, `"motor": "hibrido"` y
`"vectores": {"alineados": true}`. En el portal, la cabecera mostrará la
etiqueta **«Búsqueda híbrida»**.

---

## 7. Si algo falla

| Síntoma | Causa probable |
|---|---|
| `Falta EMBEDDINGS_API_KEY` | No configuraste la variable en Vercel |
| `Error HTTP 401` | La clave no es válida, está revocada o **le falta el prefijo** (`hf_`, `sk-`) |
| `Error HTTP 404` | El modelo no existe o tu cuenta no tiene acceso |
| `/api/health` sigue en `keyword` | Falta la variable en Vercel, no se redesplegó, o `n` no coincide con el corpus |
| `vectores.alineados: false` | El corpus cambió después de vectorizar: vuelve a ejecutar §1 |
| Los resultados empeoran | Prueba otro `alpha` (0 = solo BM25, 1 = solo semántico) |
| `torch.cuda.is_available()` es `False` | Instalación solo-CPU. No es un error si vectorizas en CPU |
| `OAuth token has expired` o `401 Repository Not Found` | Hay un token caducado en `~/.cache/huggingface`. Define `HF_HOME` a una caché propia, o `HF_HUB_OFFLINE=1` si el modelo ya está descargado |

---

## 8. Preguntas frecuentes

**¿Y si cambio de proveedor de embeddings?**
Cambia `EMBEDDINGS_BASE_URL` y `EMBEDDINGS_MODEL`, vuelve a vectorizar y
reconfigura. El formato es el de OpenAI, así que sirven DeepInfra, Jina, Voyage…
DeepInfra, por ejemplo, sirve `BAAI/bge-m3`.

**¿Puedo usar un modelo más preciso?**
Sí: `EMBEDDINGS_MODEL=text-embedding-3-large` (3 072 dimensiones, ~33 MB de
vectores). En la evaluación no superó a las alternativas locales, pero puedes
medirlo con `scripts/comparar_recuperacion.py` antes de decidir.

**¿Cuándo hay que repetirlo?**
Solo si cambia el corpus (nuevas normas) o si cambias de modelo. Al
re-vectorizar, el script reescribe ambos archivos completos.
