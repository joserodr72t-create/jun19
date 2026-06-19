# Práctica — Agente con ADK, Skills, MCP y RAG en Vertex AI Agent Engine
## Bloque 2: Prompt modular, Skills, MCP (Maps) y RAG

> **Punto de partida:** Bloque 1 completado (Cloud Shell, `setvars.sh`, APIs habilitadas, repo clonado en `~/next-26-keynotes/devkey/demo-1`, ADK instalado y agente base probado).
>
> **En este bloque** convertimos el agente genérico en el planificador real: instrucción **modular** con `PromptBuilder`, **Skills** cargadas dinámicamente (`SkillToolset`), **herramientas MCP de Google Maps** (clave en **Secret Manager**) y nuestra **extensión RAG** — un corpus en **Vertex AI RAG Engine** sobre documentos en Cloud Storage, consultado por un **sub-agente de recuperación** que responde **con citas**. Lo probaremos en local con `adk web`.

Antes de empezar, recarga variables y activa el entorno si se ha cerrado la sesión:

```bash
source ~/setvars.sh
cd ~/next-26-keynotes/devkey/demo-1
source .venv/bin/activate
```

---

## 1. Instrucción modular con `PromptBuilder`

Las instrucciones (system prompt) dictan el comportamiento del agente. En vez de una cadena gigante, el proyecto compone el prompt por **secciones** (`planner_agent/prompts.py`): `ROLE`, `RULES`, `WORKFLOW`, `SKILLS`, `TOOLS`, ensambladas por `PromptBuilder` (`planner_agent/utils.py`).

Hay dos versiones predefinidas:
- `PLANNER_INSTRUCTION_NO_TOOLS` — sin mención a herramientas (para probar el razonamiento puro).
- `PLANNER_INSTRUCTION` — con skills y tools.

En `planner_agent/agent.py`, localiza el `TODO: Replace Instruction and Description` y **descomenta** la versión sin tools:

```python
instruction=PLANNER_INSTRUCTION_NO_TOOLS
description="Expert GIS analyst for marathon route and event planning."
```

Pruébalo:

```bash
uv run adk run planner_agent
```

```
[user]: Plan a marathon for 10000 participants in Madrid on April 24, 2027 in the evening timeframe
```

El plan ya es mucho más rico y estructurado. **Por qué importa:** un *PromptBuilder* modular permite intercambiar secciones (añadir restricciones, quitar el workflow) en tiempo de ejecución sin reescribir toda la instrucción. Escribe `exit` para salir.

---

## 2. Activar Skills y herramientas

Ahora pasamos a la instrucción completa y cargamos las herramientas. En `planner_agent/agent.py`, busca `TODO: Replaces Tools` y **descomenta**:

```python
instruction=PLANNER_INSTRUCTION
tools=get_tools()
```

Eso es todo el cambio de código. **Qué son las Skills:** una *Skill* es una unidad autocontenida de funcionalidad (instrucciones + recursos + herramientas) que el agente carga **incrementalmente** para no saturar la ventana de contexto. El proyecto define 3 skills en `planner_agent/skills/`:

1. **gis-spatial-engineering** — procesa GeoJSON para crear la ruta de la maratón.
2. **mapping** — usa las herramientas de Google Maps para buscar lugares e info meteorológica.
3. **race-director** — valida que la ruta cumple las guías de planificación.

La función `get_tools()` (en `planner_agent/tools.py`) descubre las skills con `load_skill_from_dir`, las envuelve en un `SkillToolset` y añade `PreloadMemoryTool()` y las herramientas de Maps:

```python
def get_tools() -> list:
    skills_dir = pathlib.Path(__file__).parent / "skills"
    skills = [load_skill_from_dir(d) for d in sorted(skills_dir.iterdir())
              if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").exists()]
    skill_toolset = SkillToolset(skills=skills,
                                 code_executor=UnsafeLocalCodeExecutor(),
                                 additional_tools=_load_additional_tools(skills_dir))
    tools = [skill_toolset, PreloadMemoryTool()]
    tools.extend(get_maps_tools())
    return tools
```

---

## 3. Herramientas MCP de Google Maps

El planificador necesita contexto espacial real (rutas, elevación, lugares). Eso se lo da el **servidor MCP de Google Maps** (Model Context Protocol). En el código actual del repo, `get_maps_tools()` (en `planner_agent/tools.py`) se conecta **directamente** al endpoint MCP de Maps con un `McpToolset` sobre HTTP *streamable*, autenticando con la API key en la cabecera `X-Goog-Api-Key`:

```python
mcpToolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://mapstools.googleapis.com/mcp",
        headers={
            "X-Goog-Api-Key": maps_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
    )
)
```

> El fichero también define una clase `MapsApiRegistry` (variante vía `ApiRegistry`), pero la ruta activa es la conexión directa por `McpToolset`. Además, `tools.py` resuelve la clave con un *fallback* automático: primero la variable `GOOGLE_MAPS_API_KEY` del entorno y, si está vacía, **lee el secreto `maps-api-key` de Secret Manager** con `gcloud`. Por eso es crítico que el secreto se llame exactamente así (lo creamos en 3.2).

### 3.1 Crear la clave de Google Maps

```bash
gcloud services enable mapstools.googleapis.com   # ya habilitada en el Bloque 1
```

Crea la API key (también puedes hacerlo desde **Google Maps Platform > Credentials** en la consola):

```bash
gcloud services api-keys create --display-name="${RESOURCE_PREFIX}-maps-key"
```

Recupera el valor de la clave (cadena que empieza por `AIza...`). Localiza el `KEY_ID` y pide su `keyString`:

```bash
KEY_ID="$(gcloud services api-keys list \
  --filter="displayName=${RESOURCE_PREFIX}-maps-key" \
  --format='value(uid)')"
export MAPS_API_KEY="$(gcloud services api-keys get-key-string "$KEY_ID" --format='value(keyString)')"
echo "Maps key: ${MAPS_API_KEY:0:8}…"
```

> En producción, **restringe** la clave a las APIs y referrers/IPs concretos que la usan.

### 3.2 Guardar la clave en Secret Manager

En vez de dejarla en texto plano, la guardamos como secreto llamado **`maps-api-key`** (el código sabe leerla de ahí):

```bash
printf '%s' "$MAPS_API_KEY" | gcloud secrets create maps-api-key --data-file=-

# si ya existe, añade una nueva versión:
# printf '%s' "$MAPS_API_KEY" | gcloud secrets versions add maps-api-key --data-file=-
```

Y la dejamos también en el `.env` para la ejecución local:

```bash
sed -i "s|^GOOGLE_MAPS_API_KEY=.*|GOOGLE_MAPS_API_KEY=${MAPS_API_KEY}|" planner_agent/.env
```

> Este paso es en realidad **opcional** en Cloud Shell: si la variable queda vacía, el propio `tools.py` recupera la clave del secreto `maps-api-key` automáticamente. Lo mantenemos para que se vean ambas vías y porque hace el arranque local más rápido (evita la llamada a `gcloud` en cada inicio).

> 🎓 **ACE — Dominio 5 (Acceso y seguridad).** Usar **Secret Manager** en lugar de credenciales en código es una buena práctica directamente alineada con el examen (gestión de secretos y mínimo privilegio).

---

## 4. Extensión RAG: corpus en Vertex AI RAG Engine

Hasta aquí seguimos el codelab oficial. Ahora añadimos **RAG** para que el agente **valide el plan contra normativa real** (seguridad de eventos, permisos, distancias homologadas) y responda **con citas** a los documentos.

### 4.1 Bucket y documentos del corpus

Crea el bucket (nombre determinista del Bloque 1) y sube tus PDFs de normativa a `gs://$RAG_BUCKET/reglamento/`:
> Los PDF de normativa de carreras/eventos están en documentos.zip. RAG Engine admite, entre otros, PDF, TXT, HTML y Markdown.


```bash
gcloud storage buckets create "gs://${RAG_BUCKET}" --location="${REGION}"

# Sube tus documentos (PDF/TXT/MD) de normativa de eventos:
gcloud storage cp ./docs/reglamento/*.pdf "gs://${RAG_BUCKET}/reglamento/"
```



> 🎓 **ACE — Dominio 2/3.** Crear buckets, elegir ubicación y cargar datos a Cloud Storage es contenido examinable (2.2 almacenamiento, 3.4 carga de datos).


### 4.2 Crear el corpus e ingerir los documentos (vía consola)


#### 4.2.1 Crear el corpus

1. En el buscador de la consola ve a **Vertex AI → RAG Engine**
   (directo: `https://console.cloud.google.com/vertex-ai/rag`).
2. Arriba, en **Region**, selecciona **us-central1 (Iowa)** — la misma `${REGION}` del Bloque 1.
   Verás también el indicador **Serverless mode**.
3. Pulsa **Create corpus** y rellena:
   - **Corpus name**: `reglamento-eventos`
   - **Description** (opcional): p. ej. "Normativa de eventos para validar el plan".
   - **Embedding model**: elige **`text-embedding-005`** (no dejes el modelo antiguo por
     defecto: `text-embedding-005` da mejor calidad y cuotas más holgadas).
   - **Vector database**: en Serverless es **Managed Agent Retrieval** (gestionado, no hay
     que configurar nada).
4. **Create**. El corpus aparece en la lista con estado **Ready**.

> 🎓 **ACE — arquitectura.** Aquí se ve, sin código, el patrón de RAG Engine: eliges
> **modelo de embeddings** + **vector DB gestionado** y el servicio se encarga del resto
> (chunking, indexado, recuperación).

#### 4.2.2 Importar los documentos

1. Haz clic en **`reglamento-eventos`** para entrar en el corpus → pestaña **Data** →
   botón **Import data**.
2. **Fuente de datos**, dos opciones:
   - **Cloud Storage** (entorno real, los docs ya están en tu bucket del Bloque 1):
     indica `gs://${RAG_BUCKET}/reglamento/`.
   - **Direct upload** (subida directa desde tu equipo): arrastra los ficheros. Es la vía
     más simple y la que usaremos si la importación desde GCS diera problemas.
3. Despliega **Advanced options** y fija el **chunking** para que coincida con la práctica:
   - **Chunk size**: `1024`
   - **Chunk overlap**: `256`
   - **Maximun Embedding Requests per minute**: `10`
   - **Parser**: deja el **parser por defecto** (los `.txt` y PDFs de texto entran sin
     problema). Solo cambia a **Layout parser / LLM parser** si tienes PDFs escaneados o muy
     complejos.
4. Lanza la importación. Al terminar, la consola muestra una tabla **por fichero** con
   **Imported / Failed** y, si algo falla, el **motivo exacto** (formato, cuota de
   embeddings, etc.). Reimporta solo lo que falle tras corregirlo.

> **Nota — formato de los documentos.** RAG Engine admite PDF, TXT, HTML y Markdown. Para
> documentos largos y densos, el **texto plano (`.txt`)** es la opción más robusta. 


#### 4.2.3 Obtener el nombre del corpus y exportarlo

El planificador y el sub-agente RAG necesitan el **nombre completo del corpus** en la variable
`RAG_CORPUS`. Localiza el **ID del corpus** en la consola: aparece en la **miga de pan**
(`Corpus: 2234964091640741888`) y en la URL al entrar en el corpus.

Construye y exporta el nombre completo (formato con número de proyecto):

```bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

# Sustituye CORPUS_ID por el ID que ves en la consola:
export RAG_CORPUS="projects/${PROJECT_NUMBER}/locations/${REGION}/ragCorpora/CORPUS_ID"


# Persistir para el resto de la sesión y para el agente:
echo "export RAG_CORPUS=${RAG_CORPUS}" >> ~/setvars.sh
echo "RAG_CORPUS=${RAG_CORPUS}"        >> planner_agent/.env

echo "RAG_CORPUS = ${RAG_CORPUS}"
```


> La **primera** creación de corpus en Serverless puede tardar un poco más de lo habitual, porque RAG Engine está aprovisionando por debajo la colección de Vector Search 2.0 en tu proyecto. Las siguientes son inmediatas.

**Qué hace RAG Engine:** ingiere los documentos, los **trocea** (chunking), genera **embeddings**, los **indexa** en el almacén vectorial gestionado y, en consulta, **recupera** los fragmentos relevantes para que Gemini responda **fundamentado y con citas**.

> 🎓 **ACE — Dominio 2/3.** El corpus se crea en `${REGION}` y lee los objetos de `gs://${RAG_BUCKET}/reglamento/`. La elección de ubicación del bucket y del corpus (misma región) y la carga de datos a Cloud Storage son contenido examinable (2.2 almacenamiento, 3.4 carga de datos).

---

### 4.4 Sub-agente de recuperación + integración como herramienta

La herramienta de recuperación de ADK (`VertexAiRagRetrieval`) **debe usarse sola dentro de una instancia de agente** (según consta en la documentación oficial de ADK). Para combinarla con las skills y Maps del planificador, la encapsulamos en un **sub-agente** y lo exponemos al planificador como herramienta (`AgentTool`). Crea `planner_agent/rag_agent.py`:

```python
# planner_agent/rag_agent.py — RAG sub-agent that answers with citations
import os
from google.adk.agents import Agent
from google.adk.tools.retrieval.vertex_ai_rag_retrieval import VertexAiRagRetrieval
from vertexai import rag   # GA import

retrieve_rules = VertexAiRagRetrieval(
    name="retrieve_event_rules",
    description="Retrieves event regulations and rules from the corpus to validate the plan.",
    rag_resources=[rag.RagResource(rag_corpus=os.environ["RAG_CORPUS"])],
    similarity_top_k=5,
    vector_distance_threshold=0.5,
)
rag_rules_agent = Agent(
    model="gemini-3.1-pro-preview",  # served on the GLOBAL endpoint
    name="rag_rules_agent",
    description="Event regulations specialist; answers by citing the corpus.",
    instruction=(
        "ALWAYS answer by querying the retrieval tool. "
        "Cite the source document for every claim. If there's no basis in the corpus, say so."
    ),
    tools=[retrieve_rules],
)
```

Y conéctalo al planificador en `planner_agent/tools.py`, dentro de `get_tools()`:

```python
from google.adk.tools.agent_tool import AgentTool
from .rag_agent import rag_rules_agent

# ... dentro de get_tools(), antes del return:
tools.append(AgentTool(agent=rag_rules_agent))
```
Además (apis adicionales para el MCP):

```bash
gcloud services enable \
  routes.googleapis.com \
  places.googleapis.com \
  directions-backend.googleapis.com \
  distance-matrix-backend.googleapis.com \
  elevation-backend.googleapis.com \
  geocoding-backend.googleapis.com \
  roads.googleapis.com \
  maps-backend.googleapis.com
```


> Así el planificador **delega** en el sub-agente RAG la validación normativa, y este responde citando la fuente. Es además un buen ejemplo de patrón **multi-agente** con ADK.
>
> **Importante — dos ubicaciones distintas, y son compatibles:** el `rag_corpus` apunta a `.../locations/${REGION}/ragCorpora/...`, de modo que la **recuperación** siempre va contra `${REGION}` (us-central1), independientemente de dónde se sirvan los modelos. La **inferencia** de los modelos Gemini 3.x (planificador y sub-agente) va por el **endpoint global**. Lo vemos en el paso 5.

---

## 5. Prueba con `adk web` en Cloud Shell (Web Preview)

En Cloud Shell **no** hay un navegador local apuntando a `localhost:8000`: la Dev UI se ve a través de **Web Preview**, que expone el puerto mediante un proxy HTTPS bajo `*.cloudshell.dev`. Eso obliga a dos cosas:

1. **Fijar el puerto** al que apunta Web Preview (usamos 8080, que es el puerto por defecto de Web Preview → un solo clic).
2. **Permitir el origen del proxy con `--allow_origins`**. Si no, la Dev UI carga pero sus llamadas al backend fallan por **CORS** (verás la UI en blanco o sin respuestas).

Arranca la Dev UI fijando puerto y orígenes permitidos:

```bash
uv run adk web --port 8080 --allow_origins "regex:https://.*\.cloudshell\.dev"
```

Cuando veas `ADK Web Server started` / `Uvicorn running`, abre el botón **Web Preview** (icono arriba a la derecha de la barra de Cloud Shell) → **Vista previa en el puerto 8080**. Se abrirá una pestaña nueva con la Dev UI.


En la Dev UI, selecciona **`planner_agent`** en el desplegable y envía:

```
Plan a marathon for 10000 participants in Madrid on April 24, 2027 in the evening timeframe, and validate it against the event safety rules
```

Deberías ver: las **skills** cargándose, **llamadas a Maps** (rutas/lugares) y una llamada al **sub-agente RAG** que devuelve la validación normativa **con citas** del corpus. Pulsa `Ctrl+C` en la terminal para parar.

> Si la UI carga pero el agente no responde, casi siempre es CORS (falta `--allow_origins`) o que el puerto de Web Preview no coincide con el de `adk web`. Si el modelo da 404, revisa `GOOGLE_CLOUD_LOCATION=global` en el `.env`.

---

## Cierre del Bloque 2

El agente ya está completo en local: **prompt modular**, **Skills**, **MCP de Maps** (clave en Secret Manager), **RAG con citas** (corpus en Vertex AI RAG Engine en **modo Serverless** + sub-agente de recuperación) y probado vía **Web Preview** de Cloud Shell.

**En el Bloque 3** lo llevamos a producción: **cuenta de servicio del runtime + IAM de mínimo privilegio**, despliegue con `adk deploy agent_engine`, prueba contra el endpoint con `main.py`, **observabilidad** en Cloud Trace/Logging, sesiones/memoria y **teardown** completo.

> 🎓 **Resumen ACE de este bloque:** Cloud Storage (bucket, ubicación, carga de datos — Dom. 2-3) y **Secret Manager** (Dom. 5). La conmutación de modo del RAG Engine y la capa ADK/MCP/RAG son comprensión de la arquitectura de agentes (no examinable en ACE, pero clave para el proyecto).
