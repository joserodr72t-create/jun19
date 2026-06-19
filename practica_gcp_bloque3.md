# Práctica — Agente con ADK, Skills, MCP y RAG en Vertex AI Agent Engine
## Bloque 3: Despliegue en Agent Engine, operación y teardown

> **Punto de partida:** Bloques 1 y 2 completados (agente con prompt modular, Skills, MCP de Maps y RAG con citas, probado en local con `adk web`).
>
> **En este bloque** llevamos el agente a producción en el runtime gestionado: **cuenta de servicio + IAM de mínimo privilegio**, despliegue con `adk deploy agent_engine`, prueba contra el endpoint, **observabilidad** (Cloud Trace/Logging), nociones de **sesiones y memoria**, y **teardown** completo de los recursos.
>
> Recuerda: Agent Engine **ejecuta el agente sobre Cloud Run de forma gestionada**; nosotros no creamos ni administramos servicios de Cloud Run directamente.

> ✅ El *service agent* de Agent Engine es `service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (AI Platform **Reasoning Engine Service Agent**), que trae por defecto el rol `roles/aiplatform.reasoningEngineServiceAgent`. Los roles adicionales de abajo siguen siendo necesarios para Maps/RAG/Storage.

Recarga variables y entorno:

```bash
source ~/setvars.sh
cd ~/jun19/Agent
source .venv/bin/activate
```

---

## 1. Cuenta de servicio e IAM de mínimo privilegio

El agente, ya en Agent Engine, se ejecuta bajo una **cuenta de servicio gestionada** (el *Reasoning Engine / Agent Engine Service Agent*). Para que pueda usar Gemini, leer el secreto de Maps y consultar el corpus RAG, esa identidad necesita los **roles mínimos** necesarios.

El *service agent* se aprovisiona automáticamente en el primer despliegue, pero como queremos concederle roles **antes** de desplegar, lo generamos manualmente (recomendación de la propia documentación para evitar fallos de "principal not found"):

```bash
gcloud beta services identity create \
  --service=aiplatform.googleapis.com --project="$PROJECT_ID"

export AE_SA="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
echo "Service agent Agent Engine: $AE_SA"
```

> Esta cuenta ya trae el rol `roles/aiplatform.reasoningEngineServiceAgent` con los permisos base del runtime. Una alternativa robusta en producción es crear una **cuenta de servicio propia** y asignarla al runtime; en esta práctica concedemos permisos al *service agent* por simplicidad.

Concede los roles necesarios (mínimo privilegio):

```bash
# Usar modelos Gemini y RAG Engine en Vertex AI
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${AE_SA}" --role="roles/aiplatform.user"

# Leer el secreto de la clave de Maps
gcloud secrets add-iam-policy-binding maps-api-key \
  --member="serviceAccount:${AE_SA}" --role="roles/secretmanager.secretAccessor"



# Comprobaciones

gcloud projects get-iam-policy "$PROJECT_ID" \
  --flatten="bindings[].members" \
  --filter="bindings.members:${AE_SA}" \
  --format="table(bindings.role)"


gcloud secrets get-iam-policy maps-api-key \
  --flatten="bindings[].members" \
  --filter="bindings.members:${AE_SA}" \
  --format="table(bindings.role)"


```

**Por qué así:** cada permiso se acota al recurso y a la acción concreta (usar Vertex AI, acceder a *un* secreto, leer *un* corpus). Es el **principio de mínimo privilegio**.

> 🎓 **ACE — Dominio 5 (Acceso y seguridad).** Crear/usar **cuentas de servicio**, asignarlas a recursos y conceder **roles IAM mínimos** es contenido central del examen (5.1 IAM, 5.2 cuentas de servicio).

---

## 2. Desplegar el agente en Agent Engine

Con el agente validado en local, despliégalo con el CLI de ADK:

Ojo, planner_agent/requirements.txt debe contener:

google-genai>=1.70.0
google-adk[extensions]==1.31.1
google-cloud-aiplatform[adk,agent_engines]
mcp==1.27.0


Y 

```bash
uv run adk deploy agent_engine \
  --env_file planner_agent/.env \
  --region=us-central1 \
  --requirements_file planner_agent/requirements.txt \
  planner_agent
```

El proceso empaqueta el código y las dependencias, construye el contenedor y lo publica en el runtime gestionado. Al terminar verás algo como:

```
✅ Created agent engine: projects/<PROJECT_ID>/locations/us-central1/reasoningEngines/<AGENT_ID>
```

Guarda el ID del agente:

```bash
# cópialo de la salida anterior:
export AGENT_ID=<AGENT_ID>
echo "export AGENT_ID=${AGENT_ID}" >> ~/setvars.sh
```

> El agente queda como un **Reasoning Engine** con endpoint seguro, listo para integrarse en frontends, chatbots u otros backends. Puedes probarlo también desde el **Agent Runtime Playground** de la consola.

> 🎓 **ACE — nota de alcance.** El **despliegue en Agent Engine NO es examinable**; el despliegue de contenedores en **Cloud Run** sí (3.3), y aquí ocurre por debajo de forma gestionada. Buen momento para señalar la diferencia entre "yo gestiono Cloud Run" y "Agent Engine lo gestiona por mí".

---

## 3. Probar el agente desplegado

El repo trae un `main.py` para hablar con el agente. Configura su `.env` (a nivel raíz de `demo-1`):

```bash
cp sample.env .env
sed -i "s/^GOOGLE_CLOUD_PROJECT=.*/GOOGLE_CLOUD_PROJECT=${PROJECT_ID}/" .env
sed -i "s/^GOOGLE_CLOUD_LOCATION=.*/GOOGLE_CLOUD_LOCATION=${REGION}/" .env
```

Lista los agentes desplegados y manda un prompt:

```bash
python main.py list
```

```
ID: <AGENT_ID> | Display Name: planner_agent
```

```bash
python main.py prompt --agent-id "${AGENT_ID}" \
  --message "Plan a marathon for 10000 participants in Las Vegas on April 24, 2027 in the evening timeframe, validated against the safety rules"
```

Recibirás la respuesta del agente **en streaming de eventos** (objetos JSON con el contenido parcial, las llamadas a herramientas, etc. — no texto plano), integrando Gemini + Maps (MCP) + la validación normativa **con citas** (RAG). `main.py` usa el SDK actual: `vertexai.Client(...).agent_engines` con `async_create_session` y `async_stream_query`.

---

## 4. Observabilidad: Cloud Trace y Cloud Logging

En el `.env` activamos **OpenTelemetry** (Bloque 1). Cada ejecución del agente genera **trazas** (qué skill se cargó, qué herramienta se llamó, latencias) y **logs**.

- **Trazas:** consola → **Trace > Trace Explorer**, filtrando por el servicio del agente. Verás el árbol de llamadas (modelo, Maps MCP, sub-agente RAG).
- **Logs:** desde la CLI puedes leer los más recientes del runtime:

```bash
gcloud logging read \
  'resource.type="aiplatform.googleapis.com/ReasoningEngine"' \
  --limit=20 --freshness=1h --format='value(timestamp, textPayload)'
```

> 🎓 **ACE — Dominio 4 (Garantizar el funcionamiento).** Ver y filtrar logs en **Cloud Logging**, y usar **Cloud Trace** para diagnosticar latencia, son objetivos del 4.6 (monitoring y logging).

---

## 5. Sesiones y memoria (concepto)

El agente incluye `PreloadMemoryTool()`, y Agent Engine ofrece **Sessions** y **Memory Bank** gestionados: permiten **mantener contexto** entre turnos y **recordar** información previa para conversaciones multi-turno. Pruébalo enviando dos prompts encadenados en el *Playground* o reutilizando un `session_id`: el agente recuerda el plan anterior y lo refina.

> Es el equivalente gestionado a la "memoria" de los agentes en Foundry/AgentCore de los competidores: estado y memoria sin que tú montes la base de datos.

---

## 6. Teardown (limpieza de recursos)

Para evitar costes, elimina **todo** lo creado. En orden:

```bash
# 1) Borrar el agente desplegado (Reasoning Engine en Agent Engine)
python main.py delete --agent-id "${AGENT_ID}"

# 2) Borrar el corpus RAG (libera el índice vectorial gestionado)
uv run python - <<'PY'
import os, vertexai
from vertexai import rag   # import GA confirmado
vertexai.init(project=os.environ["PROJECT_ID"], location=os.environ["REGION"])
rag.delete_corpus(name=os.environ["RAG_CORPUS"])
print("Corpus borrado:", os.environ["RAG_CORPUS"])
PY

# 3) Borrar el bucket y su contenido
gcloud storage rm --recursive "gs://${RAG_BUCKET}"

# 4) Borrar el secreto de la clave de Maps
gcloud secrets delete maps-api-key --quiet

# 5) (Opcional) Borrar la API key de Maps
KEY_ID="$(gcloud services api-keys list --filter="displayName=${RESOURCE_PREFIX}-maps-key" --format='value(uid)')"
[ -n "$KEY_ID" ] && gcloud services api-keys delete "$KEY_ID" --quiet
```

Si creaste un **proyecto** solo para la práctica, puedes borrarlo entero para eliminar cualquier recurso residual:

```bash
gcloud projects delete "$PROJECT_ID"
```

> 🎓 **ACE — Dominio 4.** El *teardown* ordenado (respetando dependencias) y la gestión del ciclo de vida de los recursos es buena práctica operativa.

---

## Cierre de la práctica

Has construido y operado, de principio a fin, un **agente de IA en el framework actual de Google** (ADK), con:
- **Prompt modular** y **Skills** dinámicas.
- **Herramientas MCP** (Google Maps) con la clave protegida en **Secret Manager**.
- **RAG con citas** mediante un sub-agente sobre un corpus de **Vertex AI RAG Engine**.
- Despliegue en el runtime gestionado **Vertex AI Agent Engine**, con **observabilidad** y **memoria**.
- **Teardown** completo.

**Qué se lleva el alumno de cara a la ACE:** aunque la capa de IA no se examina, ha ejercitado de verdad piezas examinables — **proyecto y APIs** (Dom. 1), **Cloud Storage** (Dom. 2-3), **Secret Manager, cuentas de servicio e IAM de mínimo privilegio** (Dom. 5) y **Cloud Logging/Trace** (Dom. 4) — y, sobre todo, ha **comprendido los componentes** de una solución de agentes en Gemini Enterprise.
