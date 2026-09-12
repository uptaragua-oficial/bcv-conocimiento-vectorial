# Opciones de alojamiento del backend

El portal (Vercel) es estático; necesita un **backend** que ejecute Weaviate,
BGE-M3 y la API FastAPI. Este documento compara las alternativas reales,
medidas contra lo que ya está construido y probado.

## Restricción encontrada

> **HuggingFace exige suscripción PRO (o Team/Enterprise en organizaciones)
> para Spaces Docker y Gradio.** El intento de creación devolvió:
> *«Static Spaces are free for everyone, but hosting Gradio and Docker Spaces
> on free cpu-basic requires a PRO subscription»*.
> Solo los **Static Spaces** siguen siendo gratuitos, y no ejecutan código
> de servidor.

Por tanto, el Space ya construido y validado (imagen Docker de 2.39 GB,
arranque en 17 s, 2 050 objetos) **no puede publicarse en el plan gratuito**.

## Consumo real del backend

| Recurso | Medición |
|---|---|
| Imagen Docker | 2.39 GB |
| RAM en ejecución | ~2.5–3 GB (BGE-M3 en CPU + Weaviate + FastAPI) |
| Arranque en frío | ~17 s (sin descargar el modelo) + descarga inicial de BGE-M3 (~2 GB) |
| CPU | 2 vCPU suficiente (latencia de consulta: 0.25–7 s) |

## Alternativas

| # | Opción | Costo | RAM | Esfuerzo | Notas |
|---|---|---|---|---|---|
| **1** | **HuggingFace PRO** | ~US$ 9/mes | 16 GB | **Nulo** | El Space ya está construido y validado; solo se publica. La opción más directa. |
| **2** | **Túnel Cloudflare** (temporal) | Gratis | — | Nulo | Ya está funcionando; ideal para *probar* Vercel hoy. Sin garantía de disponibilidad y requiere que la máquina local esté encendida. |
| **3** | **Oracle Cloud Always Free** | Gratis | 24 GB (ARM) | Medio | Capacidad de sobra, sin límite de tiempo. Requiere crear cuenta (con tarjeta de verificación) y desplegar el contenedor. |
| **4** | **Google Cloud Run** | Capa gratuita | hasta 8 GB | Medio | 180 000 vCPU-s y 360 000 GiB-s/mes gratis. Requiere cuenta GCP con facturación habilitada. El arranque en frío es lento si no se hornea el modelo en la imagen. |
| **5** | **Backend ligero en capa gratuita** (Render / Koyeb / Fly) | Gratis | 512 MB | **Alto** | Obliga a cambiar BGE-M3 por un modelo pequeño (~120 MB) y Weaviate por un índice en proceso (FAISS + BM25). Coste de rendimiento: la evaluación mostró que BM25 es ya la estrategia más fuerte del corpus. |
| **6** | **Todo en Vercel** (sin backend aparte) | Gratis | — | **Alto** | Funciones serverless con índice BM25 precalculado + proxy a Groq. No requiere ningún servidor, pero pierde la búsqueda densa con BGE-M3 y limita el tamaño del corpus a los límites de la función. |

## Recomendación

- **Para probar hoy:** opción **2** (túnel), que ya está operativa. En Vercel
  basta apuntar el portal a la URL pública mediante el botón **⚙ Backend**
  (se guarda en el navegador, sin recompilar) o con `?api=<url>`.
- **Para producción:** opción **1** (HF PRO) si se acepta el costo mensual —es
  la de menor esfuerzo porque el Space ya está hecho y verificado—, u opción
  **3** (Oracle Cloud) si se prefiere costo cero con más trabajo de despliegue.

## Decisión pendiente del BCV / responsable del proyecto

1. ¿Se asume la suscripción de HuggingFace PRO?
2. ¿O se despliega el contenedor en otra infraestructura (Oracle, GCP)?
3. ¿O se opta por un backend ligero (opción 5/6) aceptando menor calidad de
   recuperación?

Mientras se decide, el portal puede probarse de extremo a extremo con el túnel.
