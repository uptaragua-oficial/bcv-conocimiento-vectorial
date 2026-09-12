# Guía de despliegue — Portal de Consultas Normativas del BCV

Arquitectura de despliegue:

```
┌─────────────────────────┐        HTTPS        ┌──────────────────────────────┐
│  Vercel (frontend SPA)  │ ──────────────────► │  HuggingFace Space (backend) │
│  React + Vite + Tailwind│   /chat  /search    │  Weaviate + BGE-M3 + FastAPI │
└─────────────────────────┘                     └──────────────────────────────┘
                                                              │
                                                              ▼
                                                    Groq API (generación LLM)
```

---

## 1. Verificación local (ya realizada)

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

## 2. HuggingFace Space (backend)

### 2.1 Crear el Space

1. Entrar a <https://huggingface.co/new-space>.
2. **Nombre:** `bcv-consulta-normativa` (o el que prefieras).
3. **SDK:** `Docker` → plantilla **Blank**.
4. **Hardware:** CPU basic (gratuito) es suficiente.
5. **Visibility:** Public o Private.

### 2.2 Publicar el contenido

El Space necesita los archivos de `space/` **más** `space/data/` (el índice
vectorial precomputado). El script de preparación los ensambla:

```bash
./scripts/prepare_space.sh /tmp/bcv-space
cd /tmp/bcv-space
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
