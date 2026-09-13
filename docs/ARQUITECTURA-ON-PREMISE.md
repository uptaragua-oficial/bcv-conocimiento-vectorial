# Arquitectura on-premise — Plataforma de Conocimiento Vectorial del BCV

Documento de arquitectura y dimensionamiento para desplegar la plataforma
**íntegramente en infraestructura del Banco Central de Venezuela**, sin depender
de servicios en la nube de terceros.

> **Estado:** propuesta para evaluación. No describe el sistema actual, sino el
> que resultaría de ejecutar el despliegue on-premise. Todo el dimensionamiento
> parte de **mediciones reales** del prototipo, no de estimaciones.

---

## 1. Por qué on-premise, y por qué no

Conviene decirlo antes de nada, porque condiciona todo lo demás.

**El argumento a favor no es económico.** El coste de los servicios en la nube
que usa hoy el prototipo es de céntimos: el rerank cuesta entre 0,15 y 0,75
dólares por cada mil consultas. Cualquier servidor con GPU cuesta miles de
dólares. **Si el único criterio fuera el costo, la nube gana.**

El argumento a favor es otro:

| Razón | Detalle |
|---|---|
| **Soberanía de la consulta** | El corpus normativo es público, pero **qué consulta un analista del BCV y cuándo** no lo es. Revela qué se está preparando antes de que se decida. Ese metadato sale hoy del país en cada consulta |
| **Independencia de proveedores** | No depender de que un servicio extranjero siga disponible, siga siendo asequible o no cambie sus condiciones |
| **Continuidad** | Sin dependencia de la conectividad internacional ni de la latencia hacia el exterior |
| **Auditoría** | Todo el código, los modelos y el registro de consultas quedan bajo control del Banco |
| **Política de seguridad** | Es previsible que la normativa interna del BCV exija que los sistemas de consulta documental no envíen datos a terceros |

**Y el coste real de on-premise** no es el hardware, es la **carga operativa**:
actualizar modelos, mantener los controladores de la GPU, respaldar, vigilar,
gestionar la energía. Este documento la dimensiona explícitamente.

---

## 2. Punto de partida: lo que ya existe y lo que se midió

No se parte de cero. El **Modo B** del proyecto ya es on-premise y está probado.

| Componente | Estado | Medición real |
|---|---|---|
| Weaviate 1.28.4 | Funcionando (Docker o binario) | HNSW `ef=128`, `efConstruction=256`, `maxConnections=32` |
| Índice vectorial | Construido e importado | 2 664 fragmentos, 258 documentos, 1 024 dimensiones |
| Corpus | Extraído y troceado | `corpus.json` 4,89 MB · `vectors.f32` 10,9 MB |
| BGE-M3 (embeddings) | Funcionando **en CPU** | 4,3 GB en disco |
| bge-reranker-v2-m3 (rerank) | Funcionando **en CPU** | 2,2 GB en disco · **16,3 s por consulta** |
| GLiNER (entidades) | Funcionando (respaldo por expresiones regulares) | 2,2 GB en disco |
| API FastAPI | Funcionando | `/search`, `/chat`, `/health`, `/stats`, `/catalogo` |
| Portal (SPA React) | Compilado | 157 kB de JavaScript |
| Contenedor único | **Construido y validado** | Imagen 2,39 GB · arranque 17 s · ~2,5–3 GB de RAM |
| Calidad de recuperación | Medida | BM25 0,862 · híbrida 0,884 · híbrida+rerank **0,926** nDCG@5 |

El contenedor de `space/` levanta Weaviate y la API juntos y **nunca se pudo
publicar** porque HuggingFace exige plan PRO para *Spaces* Docker. Un servidor
propio no tiene esa restricción: ese trabajo ya está hecho y es reutilizable.

### Equipo disponible hoy

| Recurso | Valor |
|---|---|
| CPU | 20 núcleos |
| RAM | 30 GB |
| Disco | 937 GB NVMe (659 GB libres) |
| GPU | NVIDIA RTX 3060 Ti, **8 GB** de VRAM |
| Controlador | 595.91.07 · CUDA 13.1 |
| Contenedores | Docker 29.7.2 |

Este equipo sirve para **piloto y validación**, no para producción (§6).

---

## 3. La decisión que define la arquitectura: el LLM

Hoy la redacción de respuestas usa DeepSeek (o Groq) por API. **On-premise
implica que la consulta no sale del edificio**, así que hay que elegir entre tres
configuraciones. Es la única decisión verdaderamente estructurante:

| | **A. Sin LLM** | **B. LLM local** | **C. LLM externo** |
|---|---|---|---|
| Redacción | extractiva: devuelve el artículo literal | generativa local | generativa en la nube |
| Sale algo del BCV | **no** | **no** | sí: la consulta y los fragmentos |
| GPU necesaria | **no** | sí | no |
| Riesgo de alucinación | **ninguno** | bajo, acotado por el contexto | bajo |
| Coste por consulta | 0 | 0 | por token |
| Calidad de redacción | — | menor que un modelo frontera | alta |

**La recuperación es idéntica en las tres.** Lo único que cambia es quién
redacta. Y en un corpus jurídico eso importa menos de lo que parece: una
respuesta extractiva —«Artículo 12. Quedan autorizados para actuar como
operadores cambiarios…» con su enlace a la fuente— es **auditable, literal y
verificable**, que es exactamente lo que un área jurídica necesita. Una
paráfrasis generada, por buena que sea, siempre exige comprobar el original.

`src/rag.py` **ya implementa el modo extractivo** y lo usa automáticamente
cuando no hay clave de LLM. La configuración A no requiere programar nada nuevo.

**Recomendación: empezar por A, añadir B cuando exista GPU de servidor, y
mantener C solo como contingencia temporal.** vLLM es el servidor de inferencia
elegido para la fase B (§7).

---

## 4. Arquitectura propuesta

```
        ┌──────────────────────────────── Red interna BCV ────────────────────────────────┐
        │                                                                                 │
   Usuario (navegador)                                                                     │
        │  HTTPS                                                                          │
        ▼                                                                                 │
  ┌───────────────────┐                                                                   │
  │  Proxy inverso    │  TLS · autenticación · límite de tasa · registro de acceso        │
  │  (nginx/Traefik)  │                                                                   │
  └────────┬──────────┘                                                                   │
           │                                                                              │
     ┌─────┴──────────────────────────────┐                                               │
     │                                    │                                               │
     ▼                                    ▼                                               │
┌──────────────────┐            ┌───────────────────────┐                                 │
│  Portal (SPA)    │            │   API FastAPI         │                                 │
│  React + Vite    │───────────▶│   /search  /chat      │                                 │
│  estático        │   /api/*   │   /health  /catalogo  │                                 │
└──────────────────┘            └───┬───────────┬───────┘                                 │
                                    │           │                                         │
                    ┌───────────────┘           └──────────────┐                          │
                    ▼                                          ▼                          │
        ┌────────────────────────┐                 ┌────────────────────────┐             │
        │  Weaviate 1.28         │                 │  Servidor de modelos   │             │
        │  HNSW + BM25           │                 │  • BGE-M3 (embeddings) │             │
        │  volumen persistente   │                 │  • bge-reranker (rerank)│            │
        │  SIN puertos públicos  │                 │  • GLiNER (entidades)  │             │
        └────────────────────────┘                 │  GPU (fp16)            │             │
                                                   └────────────────────────┘             │
                                                              │                            │
                                                   ┌──────────┴───────────┐                │
                                                   │  vLLM (fase B)       │                │
                                                   │  OpenAI-compatible   │                │
                                                   │  GPU                  │                │
                                                   └──────────────────────┘                │
                                                                                          │
        ┌──────────────────────────────────────────────────────────────────────┐          │
        │  Volúmenes:  weaviate_data · modelos HF · corpus · registros · copias │          │
        └──────────────────────────────────────────────────────────────────────┘          │
        └─────────────────────────────────────────────────────────────────────────────────┘
```

### Decisiones de diseño

- **Un solo punto de entrada.** Nada salvo el proxy inverso se publica. Weaviate
  y el servidor de modelos viven en una red Docker interna sin puertos al
  exterior. Hoy Weaviate corre con acceso anónimo habilitado: eso debe cambiar
  antes de exponerlo a una red corporativa.
- **Los modelos, en un contenedor aparte del API.** Permite reiniciarlos,
  escalarlos o cambiar el modelo sin tocar la API, y aislar el consumo de VRAM.
- **vLLM como servicio independiente** (§7). Expone una API **compatible con
  OpenAI**, de modo que `src/rag.py` lo consume con el mismo código que hoy usa
  para DeepSeek: solo cambia la URL base. **No hay que reescribir el RAG.**
- **El portal es estático.** Se sirve como ficheros; no necesita runtime. El
  botón **⚙ Backend** del portal ya permite apuntarlo a cualquier URL sin
  recompilar, así que la migración es reversible.

### Sobre el rerank en on-premise

El cliente de rerank construido para DeepInfra **habla HTTP y no conoce al
proveedor**. En on-premise se apunta a un servidor local y el rerank deja de
salir del edificio:

```bash
RERANK_API_URL=http://reranker:80/rerank
```

Con una salvedad técnica verificada: **HuggingFace Text Embeddings Inference
(TEI) no usa el formato estándar**. Su endpoint es `POST /rerank` con
`{"query": ..., "texts": [...]}` en lugar de `{"model", "query", "documents",
"top_n"}`. Es un dialecto más, y añadirlo al cliente es un trabajo pequeño y
acotado (el módulo ya soporta dos y está cubierto por 18 pruebas). Alternativa:
mantener el cross-encoder en proceso dentro del API, que es como funciona hoy.

---

## 5. Plan por fases

### Fase 1 — Portal on-premise sin LLM *(no requiere GPU)*

**Objetivo:** un portal completo que funcione dentro del BCV y no envíe nada al
exterior.

| Entregable | Detalle |
|---|---|
| Corpus actualizado | Regenerar `space/data` (está congelado en 2 050 fragmentos; el corpus real tiene 2 664) |
| Contenedor único | Weaviate + API + portal estático, sobre el `space/Dockerfile` ya existente |
| Proxy inverso | TLS con certificado interno, autenticación, límite de tasa |
| Red aislada | Weaviate sin puertos públicos y con autenticación activada |
| Respuestas | **Extractivas**: artículo literal + enlace a la fuente |
| Respaldos | Volumen `weaviate_data` + corpus + registros |

**Criterios de aceptación:** el portal responde, cita el artículo correcto para
las consultas de referencia, y **ninguna conexión saliente** es necesaria para
operar. Verificable con el cortafuegos cerrado.

**Esfuerzo estimado:** días, no semanas. La mayor parte del trabajo ya está hecha.

### Fase 2 — LLM local con vLLM *(requiere GPU de servidor)*

| Entregable | Detalle |
|---|---|
| vLLM en contenedor | Modelo cuantizado servido con API compatible con OpenAI |
| Proveedor local en `src/rag.py` | Tercer proveedor con `LLM_BASE_URL` y `LLM_MODEL` |
| Embeddings en GPU | `src/embeddings.py` fuerza hoy `device="cpu"`; hacerlo configurable |
| Rerank local | Apuntar `RERANK_API_URL` al servidor local (o mantenerlo en proceso) |
| Comparación de calidad | Medir las respuestas locales contra el modo extractivo antes de activarlas |

**Criterios de aceptación:** latencia por respuesta inferior a 15 s con 5 usuarios
simultáneos, y ausencia de afirmaciones no sustentadas por el contexto recuperado
en una muestra revisada por el área jurídica.

**Importante:** la fase 2 **no sustituye** el modo extractivo; lo complementa. El
modo extractivo debe permanecer como respaldo y como opción de auditoría.

### Fase 3 — Endurecimiento y operación

- Weaviate con autenticación por clave de API y TLS interno.
- Copias de seguridad automáticas y **restauración probada** (no basta con
  respaldar: hay que ensayar la restauración).
- Métricas y alertas (Prometheus + Grafana; vLLM y Weaviate ya exponen métricas).
- Registro de auditoría de consultas, con retención definida.
- Automatización de la actualización del corpus (ya existe el pipeline y los
  trabajos son reanudables).
- Procedimiento documentado de actualización de modelos y de la GPU.

---

## 6. Dimensionamiento

### Presupuesto de VRAM del stack de recuperación (fp16)

| Modelo | Parámetros | VRAM aproximada |
|---|---:|---:|
| BGE-M3 (embeddings) | 568 M | ~1,2 GB |
| bge-reranker-v2-m3 (rerank) | 568 M | ~1,2 GB |
| GLiNER multi (entidades) | ~200 M | ~0,5 GB |
| Activaciones y caché | — | ~0,5–1 GB |
| **Total recuperación** | | **~3,5–4 GB** |

### Presupuesto de VRAM del LLM

Cifras **aproximadas**: los pesos cuantizados varían según el formato y el
modelo, y vLLM reserva además memoria para la caché KV (por defecto, hasta el
90 % de la VRAM disponible).

| Modelo | Cuantización | Pesos | VRAM recomendada |
|---|---|---:|---:|
| 7–8B (Qwen3-8B, Llama-3.1-8B) | FP8 / 4 bits | 5–9 GB | **16–24 GB** |
| 14B (Qwen3-14B) | FP8 / 4 bits | 9–15 GB | **24 GB** |
| 32B (Qwen3-32B) | FP8 / 4 bits | 19–33 GB | **48 GB** |
| 70B | 4 bits | ~40 GB | 48 GB (muy justo) o 2×48 GB |

### Dos configuraciones

| | **Piloto** (equipo actual) | **Producción BCV** |
|---|---|---|
| GPU | RTX 3060 Ti, 8 GB | 1× L40S 48 GB o RTX 6000 Ada 48 GB |
| Uso de la GPU | **solo LLM** (7–8B cuantizado) | LLM 14–32B **y** recuperación, todo en GPU |
| Recuperación | CPU (0,25–7 s por consulta) | GPU (<1 s) |
| Rerank | API externa o CPU | local en GPU (decenas de ms) |
| CPU / RAM | 20 núcleos / 30 GB | 16–32 núcleos / 128 GB |
| Disco | 937 GB NVMe | 2× 1,92 TB NVMe en RAID 1 |
| Usuarios simultáneos | 1–5 | 10–30 |
| Alimentación | SAI obligatorio | SAI + fuentes redundantes |

**Por qué la 3060 Ti no sirve para producción:** 8 GB de VRAM no permiten
tener a la vez el stack de recuperación (~4 GB) y un LLM de 7–8B (5–9 GB). Hay
que elegir, y ninguna de las dos mitades queda bien. Además es una tarjeta de
escritorio: sin memoria ECC, sin fuente redundante, sin gestión remota y sin
perfil de ventilación para chasis de servidor.

### Por qué una GPU de 48 GB y no de 24 GB

Con 24 GB el sistema funciona, pero obliga a decidir entre un modelo de 14B y la
recuperación en GPU. Con 48 GB caben las dos cosas **y** un modelo de 32B, que es
donde la redacción en español alcanza una calidad defendible para uso
institucional. La diferencia de precio entre ambas opciones es mucho menor que el
coste de quedarse corto y tener que volver a comprar.

---

## 7. vLLM como servidor de inferencia

### Por qué vLLM

- **API compatible con OpenAI.** `src/rag.py` ya consume ese formato para
  DeepSeek: basta añadir un proveedor que apunte a `http://vllm:8000/v1`. Es un
  cambio de decenas de líneas, no una reescritura.
- **PagedAttention y *continuous batching*.** Atiende varias consultas a la vez
  sin desperdiciar VRAM, que es justo lo que hace falta en un portal con varios
  analistas.
- **Caché de prefijo automática.** En un portal RAG el prompt de sistema y las
  instrucciones se repiten en cada consulta; reutilizarlos reduce la latencia de
  forma apreciable.
- **Amplio soporte de cuantización**: FP8, INT8, INT4/AWQ, GPTQ, BitsAndBytes y
  GGUF, además de caché KV cuantizada. Permite elegir el equilibrio entre calidad
  y VRAM sin cambiar de servidor.
- **Salidas estructuradas y métricas** listas para Prometheus.

### Esquema de arranque

```bash
docker run --gpus all --restart unless-stopped \
  -v /srv/modelos:/modelos \
  --network bcv-interna \
  --name bcv-vllm \
  vllm/vllm-openai:latest \
  --model /modelos/Qwen3-14B-AWQ \
  --served-model-name bcv-llm \
  --quantization awq \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.85 \
  --enable-prefix-caching
```

Y en el entorno del API:

```bash
LLM_BASE_URL=http://bcv-vllm:8000/v1
LLM_MODEL=bcv-llm
LLM_API_KEY=local          # vLLM no valida la clave, pero el código la exige
```

`--max-model-len 8192` es suficiente porque el contexto RAG son 5 fragmentos de
unos 500 tokens más la pregunta. No hace falta un contexto de 128k, y reducirlo
ahorra VRAM de caché KV.

### Elección del modelo

Criterios: buen desempeño **en español**, licencia permisiva para uso
institucional, y encaje en la VRAM. La familia **Qwen3** cumple los tres y se
sirve bien con vLLM; conviene **evaluarla con el propio corpus** antes de
decidir, igual que se hizo con los modelos de embeddings y de rerank, en lugar de
guiarse por tablas comparativas ajenas al dominio.

---

## 8. Seguridad

| Área | Situación actual | Requisito on-premise |
|---|---|---|
| Autenticación | **ninguna** | Proxy con autenticación corporativa (LDAP/AD del BCV) o clave de API |
| Autorización | ninguna | Perfil de consulta y perfil de administración |
| TLS | no | Certificado interno; HTTPS obligatorio |
| Weaviate | acceso anónimo activado | Clave de API, TLS y red interna sin publicar |
| Secretos | variables de entorno | Gestor de secretos; no en ficheros versionados |
| Auditoría | `queries.jsonl` y `chat.jsonl` | Registro con usuario, marca de tiempo y retención definida |
| Salida a Internet | necesaria hoy | **ninguna** en régimen de operación |
| Actualización de modelos | automática desde HuggingFace | Espejo interno: los pesos se descargan y verifican una vez |

El último punto es importante y se olvida con frecuencia: en Fase 1 el sistema
debe poder **arrancar sin conexión a Internet**. Los modelos se descargan una vez
y se copian al servidor; lo contrario deja una dependencia externa en el momento
del arranque.

---

## 9. Operación

| Aspecto | Recomendación |
|---|---|
| **Energía** | SAI dimensionado para apagado ordenado. Los cortes ya han interrumpido dos procesos largos en este proyecto; los trabajos son reanudables, pero la base vectorial necesita apagado limpio |
| **Respaldos** | `weaviate_data`, corpus y registros. Frecuencia diaria; retención según política del BCV. **Probar la restauración** |
| **Supervisión** | vLLM y Weaviate exponen métricas; Prometheus + Grafana con alertas de VRAM, latencia y cola |
| **Actualización del corpus** | El pipeline de ingesta ya existe y es reanudable. Ejecutarlo en ventana de mantenimiento; después, reindexar (los guiones ya evitan duplicados) |
| **Actualización de modelos** | Cambiar el modelo de embeddings **obliga a re-vectorizar todo el corpus**. Es una operación de horas, no de minutos: planificarla, no improvisarla |
| **Registro de cambios** | Todo el proyecto está en Git con integración continua: 18 pruebas de Python y 41 de JavaScript. Mantener esa disciplina |

---

## 10. Costos indicativos

> **Advertencia:** los precios de hardware varían mucho según el canal, el
> Distribuidor y el país, y en Venezuela influyen además el transporte, el
> seguro y los trámites de importación. Las cifras siguientes son **órdenes de
> magnitud** para comparar alternativas, **no cotizaciones**.

| Concepto | Rango indicativo (USD) |
|---|---:|
| GPU 24 GB (L4 / A10) | 2 500 – 5 000 |
| GPU 48 GB (L40S / RTX 6000 Ada) | 7 000 – 11 000 |
| Servidor (CPU, 128 GB RAM, NVMe RAID, fuentes redundantes) | 8 000 – 15 000 |
| SAI para el conjunto | 500 – 1 500 |
| **Piloto sobre el equipo actual** | **0** (ya se dispone de él) |
| **Producción con GPU de 48 GB** | **~15 000 – 27 000** |

**Contrapartida anual:** el servicio en la nube que usa hoy el prototipo cuesta
**menos de un dólar al mes** con el volumen actual (el rerank, entre 0,15 y 0,75
dólares por mil consultas; la generación, céntimos por consulta). Incluso con uso
institucional intensivo —decenas de miles de consultas al año— no llega a tres
cifras. Por tanto:

- **On-premise no se justifica por ahorro.** Se justifica por soberanía,
  continuidad y control, tal como se argumenta en §1.
- El coste dominante no es la compra, es **mantener** el sistema: personal,
  actualizaciones, respaldos y energía.

---

## 11. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| La 3060 Ti no rinde para producción | Alto | Fase 1 sin GPU; no comprar hasta validar con usuarios reales |
| Calidad del LLM local por debajo de lo esperado | Medio | El modo extractivo es el respaldo y sigue siendo válido por sí solo |
| Complejidad operativa subestimada | Alto | Empezar por Fase 1, que casi no añade operación |
| Cortes de energía | Alto | SAI + apagado ordenado + reanudación de trabajos (ya implementada) |
| Dependencia de Internet en el arranque | Medio | Espejo interno de modelos; arranque sin conexión |
| Cambio de modelo de embeddings | Medio | Re-vectorización planificada; el sistema detecta el desajuste y cae a BM25 |
| Falta de personal para operar | Alto | Fase 1 no requiere especialista en GPU; la Fase 2 sí |

---

## 12. Qué falta en el código

Inventario concreto de lo que habría que modificar. Nada de esto es grande; lo
importante es saber **qué** es.

| # | Cambio | Fichero | Tamaño |
|---|---|---|---|
| 1 | Proveedor LLM local (compatible con OpenAI) | `src/rag.py` | ~20 líneas |
| 2 | `device` configurable en embeddings | `src/embeddings.py` (línea 40, hoy fija en `"cpu"`) | ~5 líneas |
| 3 | Servir el portal estático | `src/api.py` o nginx delante | ~10 líneas |
| 4 | Autenticación y TLS | proxy inverso | configuración |
| 5 | Weaviate con autenticación | `docker-compose.yml` | configuración |
| 6 | Dialecto TEI en el cliente de rerank | `web/api/_lib/rerank.js` | ~30 líneas |
| 7 | Regenerar `space/data` con el corpus de 2 664 fragmentos | `scripts/` | ejecución |
| 8 | `docker-compose` único del stack completo | nuevo | ~80 líneas |

---

## 13. Decisiones que corresponden al BCV

1. **¿Se adopta la configuración A (sin LLM) como primera etapa?** Es la única
   que no exige comprar nada y la que no envía datos al exterior.
2. **¿Se aprueba la compra de una GPU de 48 GB para producción**, o se opta por
   24 GB asumiendo el compromiso entre tamaño del modelo y recuperación en GPU?
3. **¿Qué modelo de lenguaje se autoriza** y con qué licencia? Debe pasar una
   revisión del área jurídica sobre las condiciones de uso.
4. **¿Puede el sistema prescindir de Internet** una vez instalado? Determina el
   diseño del espejo de modelos.
5. **¿Qué política de retención** se aplica al registro de consultas?
6. **¿Quién opera el sistema** y con qué capacitación?

---

## 14. Recomendación final

1. **Desplegar la Fase 1 ahora**, sobre el equipo disponible y sin comprar nada.
   Es un portal completo, con citas literales, que no envía nada al exterior.
2. **Validar con usuarios reales del BCV** durante algunas semanas, midiendo qué
   consultas se hacen y cuáles no obtienen respuesta. Eso informa a la vez el
   dimensionamiento y la ampliación del corpus.
3. **Decidir la compra de GPU con datos de uso**, no antes. Y si se compra,
   **48 GB**.
4. **Añadir el LLM local con vLLM** cuando la GPU esté disponible, comparando su
   calidad contra el modo extractivo antes de activarlo por defecto.
5. **Mantener el modo extractivo** en todos los casos, como respaldo y como
   opción de auditoría.

Y una observación que trasciende la infraestructura: la limitación principal de
esta plataforma **no es el cómputo, es el corpus**. Sus consultas más difíciles
—los requisitos para ser operador cambiario, por ejemplo— no fallan por falta de
potencia, sino porque la norma que los contiene no está entre las fuentes
recogidas. Cualquier inversión en hardware debe ir acompañada de la incorporación
de **Gaceta Oficial y SUDEBAN**; sin eso, la plataforma será rápida respondiendo
que no lo sabe.
