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
│  │ (estático)         │      │  BM25 sobre el corpus   │  │
│  └────────────────────┘      │  (2 083 fragmentos)     │  │
│                              └───────────┬────────────┘  │
└──────────────────────────────────────────┼───────────────┘
                                           ▼
                            DeepSeek / Groq API (opcional, LLM)
```

- **Recuperación:** BM25 en JavaScript puro (índice construido en ~80 ms;
  búsqueda en 1–3 ms). Se eligió por evidencia: en la evaluación del corpus,
  BM25 obtuvo el mejor nDCG@5 (0.863) frente a la semántica (0.524) y la
  híbrida (0.844).
- **Ventaja:** costo cero, sin servidores, arranque inmediato, sin límites de
  memoria para el modelo de embeddings.
- **Costo:** no incluye búsqueda densa con BGE-M3 ni Weaviate (disponibles en
  el Modo B).

### Desplegar

1. <https://vercel.com/new> → importar `uptaragua-oficial/bcv-conocimiento-vectorial`.
2. **Root Directory:** `web` *(recomendado)*.
3. **Variable de entorno (opcional):** `DEEPSEEK_API_KEY` para respuestas redactadas
   (si prefieres Groq, usa `GROQ_API_KEY`; se elige DeepSeek primero).
4. **Deploy.** Listo: el portal funciona sin configurar nada más.

> **También funciona dejando el Root Directory en la raíz del repositorio.**
> El `vercel.json` de la raíz compila `web/` y los re-exports de `api/*.js`
> delegan en `web/api/*.js`. Ambas configuraciones están verificadas con
> `npm run trace` (el corpus entra en el bundle en las dos).

#### Si el build falla con «does not define a top-level app FastAPI instance»

Ese error aparece cuando Vercel construye desde **la raíz del repositorio** y
detecta el proyecto Python. Ocurre en dos casos:

- **Configura el Root Directory como `web`** (lo más simple), o
- **Vuelve a desplegar** con el `vercel.json` de la raíz, que fuerza el preset
  «Other», compila el frontend y expone las funciones de `api/`.

Si el proyecto ya estaba creado con la raíz como Root Directory, basta con
**redesplegar** para que tome el `vercel.json` nuevo; no hace falta recrearlo.

### Búsqueda semántica en Vercel (opcional)

El modo nativo funciona solo con BM25. Para pasar a **búsqueda híbrida**
(BM25 + similitud coseno) **sin backend dedicado**:

1. **Vectoriza el corpus una sola vez**, fuera de línea:

   ```bash
   export EMBEDDINGS_API_KEY=sk-...          # o OPENAI_API_KEY
   python -m scripts.export_openai_embeddings
   ```

   Genera `web/api/_data/vectors.f32` y `embeddings_meta.json`. El orden de los
   vectores coincide con el de `corpus.json`, que es lo que garantiza que el
   coseno apunte al fragmento correcto. Commitea ambos archivos.

2. **Configura las mismas variables en Vercel.** El modelo debe coincidir con el
   usado al vectorizar, o el sistema cae a BM25 avisando por consola:

   | Variable | Valor |
   |---|---|
   | `EMBEDDINGS_API_KEY` | tu clave |
   | `EMBEDDINGS_BASE_URL` | `https://api.openai.com/v1` (por defecto) |
   | `EMBEDDINGS_MODEL` | `text-embedding-3-small` (por defecto) |

3. **Redespliega.** `/api/health` y `/api/catalogo` indicarán
   `recuperacion: hibrida`, y el portal mostrará «Búsqueda híbrida».

> La consulta se vectoriza **dentro de la función serverless** con una llamada
> HTTP al proveedor; los vectores del corpus ya están calculados. Si no hay
> clave, vectores, o el modelo no coincide, la búsqueda vuelve a BM25
> automáticamente y sin errores.

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
npm run dev:vercel     # http://localhost:3000  (frontend + /api/*)
```

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
