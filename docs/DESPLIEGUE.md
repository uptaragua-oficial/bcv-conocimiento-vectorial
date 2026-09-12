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
                                  Groq API (opcional, LLM)
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
2. **Root Directory:** `web`.
3. **Variable de entorno (opcional):** `GROQ_API_KEY` para respuestas redactadas.
4. **Deploy.** Listo: el portal funciona sin configurar nada más.

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
| `GROQ_API_KEY` | Tu clave de <https://console.groq.com/keys> |
| `GROQ_MODEL` | `openai/gpt-oss-120b` (opcional) |
| `CORS_ORIGINS` | La URL de tu app en Vercel (opcional; por defecto `*`) |

Sin `GROQ_API_KEY` el asistente funciona en **modo extractivo** (devuelve los
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
