# Building ADK Agents with Skills and Tools: Marathon Planner Agent

This repository contains the source code for the codelab **"Building ADK Agents with Skills and Tools"**, where you build a sophisticated Marathon Planner Agent using the Agent Development Kit (ADK). 

The agent progressively demonstrates capabilities such as well-structured system prompts via a prompt builder, dynamic skill loading, and mapping Model Context Protocol (MCP) tools for real-world location context. Finally, it demonstrates how to deploy the agent to the Google Cloud Agent Engine.

## Project Structure

*   `index.lab.md`: The detailed step-by-step instructions for the codelab.
*   `planner_agent/`: Contains the core code for the ADK agent:
    *   `agent.py`: The main entry point initializing the agent.
    *   `prompts.py` / `utils.py`: A prompt builder to construct logical instructions.
    *   `tools.py`: Tool registry mapping skills and MCP tools.
    *   `skills/`: Directory containing dynamic skills (like gis-spatial-engineering, mapping, and race-director).
    *   `sample.env`: Sample environment file.
*   `main.py`: A helper Python CLI script to interact with your agent once it is deployed to Google Cloud Agent Engine.

## Prerequisites

*   A Google Cloud project with billing enabled.
*   [uv](https://github.com/astral-sh/uv) package manager installed.
*   A Google Maps API key (for the mapping MCP tools).

## Getting Started

1.  **Set up the Python environment:**
    ```bash
    uv venv
    source .venv/bin/activate
    uv sync
    ```

2.  **Configure environment variables:**
    Copy the sample environment file to `.env`:
    ```bash
    cp planner_agent/sample.env planner_agent/.env
    ```
    Update `planner_agent/.env` with your `GOOGLE_CLOUD_PROJECT` and `GOOGLE_MAPS_API_KEY`.

3.  **Run the agent locally (Terminal):**
    ```bash
    uv run adk run planner_agent
    ```

4.  **Run the agent locally (Web UI):**
    To see the agent in action with skill loading and tool call visibility:
    ```bash
    uv run adk web
    ```
    Access the UI at `http://127.0.0.1:8000`.

## Deployment

Deploy the agent to the Google Cloud Agent Engine securely:

```bash
uv run adk deploy agent_engine \
  --env_file planner_agent/.env \
  planner_agent
```

## Interacting with the Deployed Agent

After deployment, you can use the provided `main.py` helper script to test the remote agent.

Make sure your root directory has an `.env` file configured with your `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.

**List deployed agents:**
```bash
python main.py list
```

**Prompt a specific agent:**
```bash
export AGENT_ID=<YOUR_AGENT_ID>
python main.py prompt --agent-id ${AGENT_ID} --message "Plan a marathon for 10000 participants in Las Vegas on April 24, 2027 in the evening timeframe"
```

**Delete a deployed agent:**
```bash
python main.py delete --agent-id ${AGENT_ID}
```

## Cleanup

To avoid incurring charges, remember to delete the resources created during the codelab. Use the `main.py delete` command to remove deployed agents and delete the Google Cloud Project if necessary.
