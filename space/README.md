---
title: Consulta Normativa BCV
emoji: ⚖️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Consultas normativas y legales del BCV con asistente RAG
---

# Consulta Normativa BCV — backend

Backend de la **Plataforma de Conocimiento Vectorial del Banco Central de
Venezuela** para el dominio jurídico-normativo. Da servicio al portal web
desplegado en Vercel.

## Qué hace

1. Levanta **Weaviate** (binario, sin Docker anidado) sobre el índice jurídico
   precomputado (2 050 fragmentos normativos, 1024 dimensiones).
2. Expone una **API FastAPI** con:

| Endpoint | Descripción |
|---|---|
| `GET /health` | Estado del servicio y de Weaviate |
| `GET /stats` | Nº de objetos y configuración HNSW |
| `GET /catalogo` | Materias y tipos de norma (para los filtros de la UI) |
| `POST /search` | Búsqueda semántica / keyword / híbrida con filtros |
| `POST /chat` | Asistente conversacional RAG con **citación de fuentes** |

## Modos de generación

- **LLM (Groq)**: si el Space tiene configurado el secreto `GROQ_API_KEY`,
  las respuestas las redacta un modelo de lenguaje.
- **Extractivo**: sin clave, el asistente devuelve los fragmentos normativos
  más relevantes con sus citas. Funciona igual, sin costo.

## Secretos recomendados

| Secreto | Obligatorio | Descripción |
|---|---|---|
| `DEEPSEEK_API_KEY` | No | Activa la generación con LLM (DeepSeek) |
| `DEEPSEEK_MODEL` | No | Modelo a usar (por defecto `deepseek-chat`) |
| `GROQ_API_KEY` | No | Alternativa a DeepSeek (Groq) |
| `CORS_ORIGINS` | No | Orígenes permitidos; por defecto `*` |

Sin ninguna clave el asistente responde en **modo extractivo**: devuelve los
fragmentos normativos recuperados con sus citas.

## Corpus

Marco legal del BCV: leyes, convenios cambiarios, resoluciones (cambiaria,
monetaria, de pagos y minerales), circulares, avisos oficiales y actos
administrativos del sistema de pagos. Cada respuesta incluye el enlace al
documento oficial en `bcv.org.ve`.

## Salvaguardas

- El asistente **informa**, no presta asesoría legal ni financiera.
- Toda respuesta se sustenta en el contexto recuperado y cita su fuente.
- Si el corpus no contiene la respuesta, se declara explícitamente.
