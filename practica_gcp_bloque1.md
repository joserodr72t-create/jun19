# Práctica — Agente con ADK, Skills, MCP y RAG en Vertex AI Agent Engine
## Bloque 1: Fundamentos y agente base

> **Qué vamos a construir (los tres bloques)**
> Un **agente planificador** (Marathon Planner) sobre el framework actual de agentes de Google — **Agent Development Kit (ADK)** — que combina **Skills** (capacidades cargadas dinámicamente), **herramientas MCP** (Google Maps vía Model Context Protocol), **RAG** (recuperación con citas sobre un corpus propio en Vertex AI RAG Engine) y se despliega en el runtime gestionado **Vertex AI Agent Engine** (parte de Gemini Enterprise Agent Platform).
>
> **Este bloque (1)** deja la base lista: entorno de **Cloud Shell**, **variables de entorno** deterministas, habilitación de **APIs**, clonado del repositorio oficial de Google, instalación de **ADK** con `uv`, y la **primera ejecución** del agente base con Gemini.

> 🎓 **Encuadre vs. examen ACE.** La capa de IA del agente (ADK, Agent Engine, MCP, RAG) **no se examina** en la Associate Cloud Engineer: sirve para **entender los componentes** de una solución de agentes en Gemini Enterprise. Pero el *envoltorio* sí es ACE puro: en cada fase marcaremos con 🎓 lo que **sí entra** en el examen (proyecto, APIs, Cloud Storage, Secret Manager, cuentas de servicio/IAM, Cloud Logging/Trace).

---

## 0. Prerrequisitos

- **Proyecto de Google Cloud** con **facturación habilitada** y permisos de `Owner` o `Editor` sobre el proyecto de laboratorio.
- **Cloud Shell** (recomendado): ya trae `gcloud`, `git` y Python. Evita instalar nada en local. Ábrela con el icono **Activar Cloud Shell** en la consola.
- Conocimientos básicos de Python.
- No necesitamos crear red: el agente corre en el runtime gestionado; **no desplegamos Cloud Run a mano**.

Comprueba que la CLI te reconoce y que hay un proyecto activo:

```bash
gcloud auth list
gcloud config get-value project
```

Si el proyecto no es el correcto, fíjalo (sustituye por tu ID):

```bash
gcloud config set project TU_PROJECT_ID
```

---

## 1. Variables de entorno (`setvars.sh`)

Cada uno usa **su propio proyecto y su región**. Para no inventar nombres ni equivocarse, centralizamos todo en un pequeño script con **naming determinista**. La región por defecto es `us-central1`, una de las tres regiones **US** que soportan Agent Engine.

Crea el fichero `setvars.sh`:

```bash
cat > ~/setvars.sh <<'EOF'
# === Identidad del proyecto ===
export PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

# === Región ===
# Agent Engine en US: us-central1 (default) | us-east4 | us-west1
export REGION="us-central1"

# === Naming determinista para los recursos que crearemos ===
export RESOURCE_PREFIX="ucm-agent"
export RUN_DATE="$(date +%Y%m%d)"
# Bucket del corpus RAG (Bloque 2). El nombre de bucket es global:
# usamos el número de proyecto para garantizar unicidad.
export RAG_BUCKET="${RESOURCE_PREFIX}-rag-${RUN_DATE}-${PROJECT_NUMBER}"

echo "PROJECT_ID    = $PROJECT_ID"
echo "PROJECT_NUMBER= $PROJECT_NUMBER"
echo "REGION        = $REGION"
echo "RAG_BUCKET    = $RAG_BUCKET"
EOF
```

Cárgalo en tu sesión (repite este `source` si abres una terminal nueva):

```bash
source ~/setvars.sh
```

**Qué hace cada variable**
- `PROJECT_ID` / `PROJECT_NUMBER`: identifican el proyecto. El **número** (no el ID) lo usamos para componer nombres globalmente únicos, como el del bucket.
- `REGION`: región única para Vertex AI, Agent Engine y el corpus RAG. Mantén la **misma** en todo el ejercicio (mezclar regiones es una causa típica de errores `NOT_FOUND`).
- `RESOURCE_PREFIX` / `RUN_DATE`: prefijo y fecha para que todos los recursos sean reconocibles y no colisionen.
- `RAG_BUCKET`: nombre del bucket del corpus RAG; se usa en el Bloque 2.

> 🎓 **ACE — Dominio 1 (Configurar el entorno).** Identificar proyecto y número, y trabajar con `gcloud config`, es base del 1.1 (configurar proyectos y cuentas).

---

## 2. Habilitar las APIs necesarias

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  mapstools.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  vectorsearch.googleapis.com
```

**Qué habilita cada API**
- `aiplatform` — **Vertex AI**: modelos Gemini, **Agent Engine** y **RAG Engine**. Es el corazón de la práctica.
- `run` — **Cloud Run**: Agent Engine **despliega el agente sobre Cloud Run de forma gestionada** (no lo manejamos nosotros, pero la API debe estar activa).
- `secretmanager` — **Secret Manager**: guardaremos ahí la clave de Google Maps (Bloque 2).
- `mapstools` — **Google Maps Platform tools**: expone el **servidor MCP de Maps** que usará el agente.
- `storage` — **Cloud Storage**: bucket del corpus de documentos para RAG (Bloque 2).
- `cloudresourcemanager` / `serviceusage` — gestión de proyecto y de servicios (requeridas por las herramientas anteriores).

Verifica que quedaron activas:

```bash
gcloud services list --enabled 
```

> 🎓 **ACE — Dominio 1 (1.1).** "Enabling APIs within projects" es un objetivo explícito del examen.

---

## 3. Clonar el repositorio y preparar el entorno con ADK

Clona el repo y entra en la demo del agente:

```bash
cd ~
git clone https://github.com/joserodr72t-create/jun19
cd june19/Agent
```

ADK se instala con **`uv`** (gestor de entornos/paquetes de Python rápido). Cloud Shell no siempre lo trae; instálalo si falta:

```bash
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
# asegura el PATH si se acaba de instalar
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

Crea el entorno virtual e instala las dependencias del proyecto (incluido ADK):

```bash
uv venv
source .venv/bin/activate
uv sync
```

**Qué estamos haciendo**
- **ADK (Agent Development Kit)** es el framework *open-source* de Google (code-first, Python) para construir y orquestar agentes y sistemas multi-agente; es el mismo que sustenta productos como Gemini Enterprise.
- `uv venv` crea un entorno aislado; `uv sync` instala exactamente las versiones fijadas en el proyecto (reproducibilidad). El `pyproject.toml` exige **Python ≥ 3.12** (Cloud Shell lo cumple) e incluye ya `google-adk`, `google-genai` y **`vertexai>=1.43.0`** — es decir, el SDK que usaremos para RAG en el Bloque 2 queda instalado sin pasos extra.

Comprueba que el CLI de ADK responde:

```bash
uv run adk --help
```

---

## 4. Configurar el agente (`.env`) y explorar `agent.py`

El agente lee su configuración de un fichero `.env`. Copia la plantilla y edítala:

```bash
cp planner_agent/sample.env planner_agent/.env
```

Edita `planner_agent/.env` (con el editor de Cloud Shell o `nano`) para que use **tu proyecto**. Debe quedar así:
.

```bash
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=TU_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_MAPS_API_KEY=PENDIENTE_BLOQUE_2
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=true
```

> Puedes rellenarlo automáticamente con las variables ya cargadas:
> ```bash
> sed -i "s/^GOOGLE_CLOUD_PROJECT=.*/GOOGLE_CLOUD_PROJECT=${PROJECT_ID}/" planner_agent/.env
> ```

**Qué significan las claves**
- `GOOGLE_GENAI_USE_VERTEXAI=1` — el agente usa **Vertex AI** como backend de Gemini (no la API pública de AI Studio). Así el modelo corre dentro de tu proyecto y región.
- `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` — proyecto y región para Vertex AI y Agent Engine.
- `GOOGLE_MAPS_API_KEY` — la rellenaremos en el Bloque 2 (de momento, *placeholder*).
- Las cuatro líneas `*_TELEMETRY` / `OTEL_*` activan **OpenTelemetry**, para capturar trazas finas del comportamiento del agente (las veremos en Cloud Trace en el Bloque 3).

Ahora abre `planner_agent/agent.py` y localiza la definición del agente. En su forma base es:

```python
instruction = "Answer user questions to the best of your knowledge"
description = "A helpful assistant for user questions."
tools = []

# # TODO: Replace Instruction and Description Prompt only
# instruction=PLANNER_INSTRUCTION_NO_TOOLS
# description="Expert GIS analyst for marathon route and event planning."

# # TODO: Replaces Tools
# instruction=PLANNER_INSTRUCTION
# tools=get_tools()

root_agent = Agent(
    model="gemini-2.5-pro",
    name="planner_agent",
    description=description,
    instruction=instruction,
    tools=tools,
)
```

Fíjate en los dos bloques `TODO` comentados: son los que iremos descomentando en el Bloque 2 para activar el prompt modular y las herramientas. El modelo es **`gemini-2.5-pro`** (Gemini Pro vía Vertex AI).

La clase **`Agent`** de ADK abstrae el historial de mensajes, la orquestación de herramientas y la comunicación con el LLM: tú solo defines **modelo**, **identidad**, **instrucción** y **herramientas**. Ahora mismo el agente es genérico (sin skills, MCP ni tools); eso lo añadimos en el Bloque 2.

---

## 5. Primera ejecución del agente base

Lanza el agente en modo conversación desde la terminal:

```bash
uv run adk run planner_agent
```

Prueba una pregunta sencilla:

```
[user]: What is the length of a Marathon
```

Deberías obtener algo como:

```
[planner_agent]: The official length of a marathon is 26.2 miles (42.195 km).
```

El agente ya responde con conocimiento del modelo Gemini, pero **todavía no sabe planificar** una maratón real (rutas, normas, mapas): le falta el prompt estructurado, las skills, las herramientas MCP y el RAG. Escribe `exit` para salir.

---

## Cierre del Bloque 1

Has dejado lista la base de la solución:
- Entorno de **Cloud Shell** con variables deterministas (`setvars.sh`).
- **APIs** habilitadas (Vertex AI, Run, Secret Manager, Maps tools, Storage).
- Repositorio oficial clonado y **ADK** instalado con `uv`.
- Agente base configurado contra **Vertex AI** y **probado** con Gemini.

**En el Bloque 2** convertiremos este agente genérico en el planificador: **prompt modular** (`PromptBuilder`), **Skills** dinámicas (`SkillToolset`), **herramientas MCP de Google Maps** (con la clave en **Secret Manager**) y la **extensión RAG** (corpus en **Vertex AI RAG Engine** sobre documentos en Cloud Storage, con respuestas **citadas**). Lo probaremos en local con `adk web`.

> 🎓 **Resumen ACE de este bloque:** configuración de proyecto y `gcloud` (Dom. 1.1) y **habilitación de APIs** (Dom. 1.1). En los siguientes bloques tocaremos Cloud Storage y Secret Manager (Dom. 2-3) y cuentas de servicio, IAM y observabilidad (Dom. 4-5).
