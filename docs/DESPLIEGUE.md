# Guía de despliegue — Portal de Consultas Normativas del BCV

Hay **dos formas** de desplegar, y la primera no necesita ningún servidor aparte.

## Modo A — Nativo de Vercel (recomendado para probar y para costo cero)

Todo vive en Vercel: el frontend **y** el backend como *funciones serverless*.
No requiere HuggingFace, ni túneles, ni servidores.

```
┌──────────────────────────────────────────────────────────┐
│                        VERCEL                            │
│  ┌────────────────────┐      ┌────────────────────────┐  │
│  │ SPA React + Vite   │─────►│  /api/chat  /api/search │  │
│  │ (estático)         │      │  BM25 + híbrida sobre   │  │
│  └────────────────────┘      │  el corpus (2 664 frag.)│  │
│                              └───────────┬────────────┘  │
└──────────────────────────────────────────┼───────────────┘
                                           ▼
                            DeepSeek / Groq API (opcional, LLM)
```

- **Recuperación:** BM25 en JavaScript puro (índice construido en ~80 ms;
  búsqueda en 1–3 ms). Si se configuran embeddings, se fusiona con la similitud
  coseno (híbrida, α=0.5); en la evaluación del corpus actual la híbrida obtuvo
  **0.884 nDCG@5** frente a **0.862** de BM25 y **0.394** de la densa sola. Sin
  proveedor de embeddings, el portal funciona igual: cae a BM25.
- **Ventaja:** costo cero, sin servidores, arranque inmediato, sin límites de
  memoria para el modelo de embeddings.
- **Costo:** no incluye búsqueda densa con BGE-M3 ni Weaviate (disponibles en
  el Modo B).

### Desplegar

1. <https://vercel.com/new> → importar `uptaragua-oficial/bcv-conocimiento-vectorial`.
2. **Root Directory:** `web` *(recomendado, lo más simple)*. También vale dejarlo
   en la raíz del repositorio: el `vercel.json` de la raíz compila `web/` y los
   re-exports de `api/*.js` delegan en `web/api/*.js`. Ambas configuraciones están
   verificadas con `npm run trace`.
3. **Variables de entorno** (Settings → Environment Variables). Las dos primeras
   son las que activan la búsqueda híbrida y el rerank; sin ellas el portal
   funciona, pero solo con BM25:

   | Variable | Valor | Para qué |
   |---|---|---|
   | `EMBEDDINGS_API_KEY` | token de Hugging Face (**`hf_…`**) | Vectorizar la consulta con `multilingual-e5-large`, el mismo modelo de los vectores del corpus |
   | `RERANK_API_KEY` | token de DeepInfra | Reordenar los candidatos con el cross-encoder |
   | `RERANK_API_URL` | `https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-0.6B` | Endpoint del rerank |
   | `DEEPSEEK_API_KEY` | clave de DeepSeek (**`sk-…`**) | Redactar la respuesta. Sin ella, responde en modo extractivo |

4. **Deploy.**

> ⚠️ **No definas `EMBEDDINGS_MODEL` ni `EMBEDDINGS_BASE_URL`.** El modelo, la URL
> y el prefijo de consulta se leen de `web/api/_data/embeddings_meta.json`, así
> que la función se configura sola. Si defines `EMBEDDINGS_MODEL` con un valor
> distinto al de la meta, el sistema detecta el desajuste y **vuelve a BM25** para
> no devolver resultados incorrectos.
>
> ⚠️ El token de Hugging Face necesita el permiso **«Make calls to Inference
> Providers»**. Un token sin ese permiso deja el portal en BM25 sin dar error.

5. **Verifica el despliegue** con una sola orden:

   ```bash
   python -m scripts.verificar_despliegue https://<tu-app>.vercel.app
   ```

   Comprueba el corpus, la alineación de los vectores, que la búsqueda semántica
   y el rerank **respondan de verdad** (no solo que estén configurados) y que la
   consulta de referencia devuelva el artículo correcto. Si algo falta, dice qué
   variable y dónde.

### Si el build falla con «does not define a top-level app FastAPI instance»

Ese error aparece cuando Vercel construye desde **la raíz del repositorio** y
detecta el proyecto Python. Ocurre en dos casos:

- **Configura el Root Directory como `web`** (lo más simple), o
- **Vuelve a desplegar** con el `vercel.json` de la raíz, que fuerza el preset
  «Other», compila el frontend y expone las funciones de `api/`.

Si el proyecto ya estaba creado con la raíz como Root Directory, basta con
**redesplegar** para que tome el `vercel.json` nuevo; no hace falta recrearlo.

### Cómo saber si está todo bien

`/api/health` informa de la **configuración**, no de si los servicios responden
de verdad: un token inválido deja el portal degradado a BM25 sin que el health
cambie. La comprobación fiable es la respuesta de una consulta real, y es lo que
mira el verificador:

```bash
curl -s -X POST https://<tu-app>.vercel.app/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"requisitos para ser operador cambiario","limit":5}' \
  | grep -o '"modo":"[a-z]*"'
```

- `"modo":"hibrida"` → embeddings funcionando.
- `"modo":"keyword"` → cayó a BM25: revisa el token de embeddings.

Y en el portal, la cabecera muestra las etiquetas **Búsqueda híbrida** y
**Rerank** cuando ambas están activas.

### Rerank

El modelo de rerank no cabe en una función serverless (2,2 GB frente al límite de
250 MB) ni en su tiempo de ejecución, así que se delega en DeepInfra. El portal
funciona igual sin configurarlo; simplemente no reordena.

Comparación de proveedores, precios y alternativa (Jina, TEI propio):
[`PROVEEDORES-RERANK.md`](PROVEEDORES-RERANK.md). Funcionamiento y medición:
[`RERANK.md`](RERANK.md).

#### Probar sin gastar créditos

El repositorio incluye un servidor de embeddings simulado:

```bash
cd web && npm run mock:embeddings     # http://127.0.0.1:9999 (8 dims)

EMBEDDINGS_API_KEY=test \
EMBEDDINGS_BASE_URL=http://127.0.0.1:9999/v1 \
EMBEDDINGS_MODEL=mock-model \
python -m scripts.export_openai_embeddings
```

> **No commitees** los vectores así generados: son de prueba. Bórralos después.

### Verificar en local (emula Vercel)

```bash
cd web
npm install
npm run build
npm run dev:vercel            # http://localhost:3000  (frontend + /api/*)

# Reproduciendo un Root Directory = repositorio (funciones en api/ de la raíz):
MODO_RAIZ=1 PORT=3099 node scripts/dev-vercel.mjs
```

Se le pueden pasar las mismas variables que en Vercel para probar la
configuración completa antes de subirla:

```bash
EMBEDDINGS_API_KEY=hf_... \
DEEPSEEK_API_KEY=sk-... \
RERANK_API_URL=https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-0.6B \
RERANK_API_KEY=... \
MODO_RAIZ=1 PORT=3099 node scripts/dev-vercel.mjs
```

Y en otra terminal, el mismo verificador que se usa contra el despliegue real:

```bash
python -m scripts.verificar_despliegue http://127.0.0.1:3099
```

El emulador sirve tanto si el despliegue usa Root Directory `web` como la raíz
del repositorio, así que una prueba en local anticipa lo que hará Vercel.

## Modo B — Backend dedicado (Weaviate + BGE-M3 + FastAPI)

Aporta búsqueda semántica e híbrida con BGE-M3 sobre Weaviate. Requiere
alojar el contenedor en algún proveedor (ver
[`BACKEND-OPCIONES.md`](BACKEND-OPCIONES.md)); HuggingFace exige plan **PRO**.

```
┌─────────────────────────┐        HTTPS        ┌──────────────────────────────┐
│  Vercel (frontend SPA)  │ ──────────────────► │  Backend dedicado            │
│  React + Vite + Tailwind│   /chat  /search    │  Weaviate + BGE-M3 + FastAPI │
└─────────────────────────┘                     └──────────────────────────────┘
                                                              │
                                                              ▼
                                                    Groq API (generación LLM)
```

El portal cambia de un modo a otro **sin recompilar**: botón **⚙ Backend** o
`?api=https://mi-backend`.

---

## 1. Verificación local del backend dedicado

```bash
# Motor vectorial
docker compose up -d

# Backend (puerto 8000)
export PYTHONPATH=.pylibs:.
uvicorn src.api:app --port 8000

# Frontend (puerto 5173)
cd web && npm install && npm run dev
```

---

## 2. Backend

> ⚠️ **Restricción vigente (verificada el 12/09/2026).** HuggingFace exige
> suscripción **PRO** para Spaces **Docker** y **Gradio**; en el plan gratuito
> solo se permiten *Static Spaces*, que no ejecutan código de servidor. El
> Space ya está construido y **validado en local** (arranque en 17 s,
> 2 050 objetos), pero **no se puede publicar sin PRO**. Ver
> [`BACKEND-OPCIONES.md`](BACKEND-OPCIONES.md) para el análisis completo.

### 2.A Prueba inmediata por túnel (sin costo)

Permite probar el portal en Vercel hoy mismo:

```bash
# 1) Backend local
docker compose up -d
export PYTHONPATH=.pylibs:.
uvicorn src.api:app --port 8000

# 2) URL pública temporal
./tools/cloudflared tunnel --url http://127.0.0.1:8000
#   → imprime algo como https://<aleatorio>.trycloudflare.com
```

En el portal desplegado, pulsar **⚙ Backend** y pegar esa URL (se guarda en el
navegador), o abrir `https://<tu-app>.vercel.app/?api=https://<aleatorio>.trycloudflare.com`.

> Limitaciones: sin garantía de disponibilidad y requiere que la máquina local
> permanezca encendida.

### 2.B HuggingFace Space (requiere PRO)

#### 2.1 Crear el Space

1. Entrar a <https://huggingface.co/new-space>.
2. **Nombre:** `bcv-consulta-normativa`.
3. **SDK:** `Docker` → plantilla **Blank**.
4. **Hardware:** CPU basic.
5. **Visibility:** Public o Private.

#### 2.2 Publicar el contenido

El Space necesita los archivos de `space/` **más** `space/data/` (el índice
vectorial precomputado). El script de preparación los ensambla:

```bash
./scripts/prepare_space.sh /home/upta/DeepSeekHarness/space-build
cd /home/upta/DeepSeekHarness/space-build
git init -b main
git remote add space https://huggingface.co/spaces/<usuario>/<space>
git add -A && git commit -m "Backend de consulta normativa del BCV"
git push space main
```

> El push a HuggingFace requiere autenticación: token de acceso (como
> contraseña) o una clave SSH registrada en tu cuenta.

### 2.3 Secretos del Space

En **Settings → Variables and secrets**:

| Secreto | Valor |
|---|---|
| `DEEPSEEK_API_KEY` | Tu clave de <https://platform.deepseek.com/api_keys> |
| `DEEPSEEK_MODEL` | `deepseek-flash` (opcional) o `deepseek-v4-pro` |
| `DEEPSEEK_THINKING` | `disabled` (por defecto) o `enabled` |
| `GROQ_API_KEY` | Alternativa a DeepSeek: <https://console.groq.com/keys> |
| `CORS_ORIGINS` | La URL de tu app en Vercel (opcional; por defecto `*`) |

> El **modo thinking** de DeepSeek viene activado por defecto con esfuerzo alto:
> añade latencia y anula `temperature`. Para un asistente que responde sobre
> contexto recuperado se desactiva por defecto; actívalo con
> `DEEPSEEK_THINKING=enabled` si prefieres priorizar la calidad del razonamiento.

Sin ninguna clave el asistente funciona en **modo extractivo** (devuelve los
fragmentos normativos con sus citas).

### 2.4 Verificar

```bash
curl https://<usuario>-<space>.hf.space/health
curl https://<usuario>-<space>.hf.space/catalogo
```

---

## 3. Vercel (frontend)

1. Entrar a <https://vercel.com/new> e **importar el repositorio**
   `uptaragua-oficial/bcv-conocimiento-vectorial`.
2. **Root Directory:** `web` (importante: el frontend está en ese subdirectorio).
3. **Framework preset:** Vite (se detecta solo; ya hay `web/vercel.json`).
4. **Environment Variables:**

   | Nombre | Valor |
   |---|---|
   | `VITE_API_URL` | `https://<usuario>-<space>.hf.space` |

5. **Deploy**.

> Si cambias `VITE_API_URL` después, hay que **redesplegar** (Vite la incrusta
> en tiempo de compilación).

---

## 4. Comprobación de extremo a extremo

1. Abrir la URL de Vercel.
2. El encabezado debe indicar **«Servicio activo»**.
3. Lanzar una consulta de ejemplo:
   *«¿Qué requisitos exige el BCV a los operadores cambiarios?»*.
4. La respuesta debe citar normas concretas (p. ej. Convenio Cambiario,
   artículos 12, 31, 69) con enlace al documento oficial.

Si aparece **«Servicio no disponible»**, revisar:
- `VITE_API_URL` correcta y redesplegada.
- El Space está en estado *Running*.
- CORS: `CORS_ORIGINS` incluye el dominio de Vercel o está en `*`.

---

## 5. Actualizaciones

| Cambio | Acción |
|---|---|
| Frontend (`web/`) | Push a GitHub → Vercel redespliega automáticamente |
| Backend (`src/`, `config/`) | Push a GitHub **y** relanzar el build del Space (el Dockerfile clona el repo) |
| Índice vectorial | `python -m scripts.export_index`, preparar y empujar el Space |
