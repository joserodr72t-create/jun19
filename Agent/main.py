# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import argparse
import asyncio
import vertexai
from dotenv import load_dotenv

load_dotenv()


async def prompt_agent(client, project_id, location, agent_id, message):
    name = f"projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}"
    remote_app = client.agent_engines.get(name=name)

    # user id is user defined. so could be anything
    remote_session = await remote_app.async_create_session(user_id="u_123")

    # we have a session
    session_id = remote_session["id"]

    print(f"Streaming response from agent {agent_id}:\n")
    async for event in remote_app.async_stream_query(
        user_id="u_123", session_id=session_id, message=message
    ):
        print(event, end="", flush=True)
    print()


def list_agents(client):
    print("Listing deployed agents...\n")
    agents = client.agent_engines.list()
    count = 0
    for agent in agents:
        agent_id = agent.api_resource.name.split("/")[-1]
        print(f"ID: {agent_id} | Display Name: {agent.api_resource.display_name}")
        count += 1
    if count == 0:
        print("No deployed agents found.")


def delete_agent(client, project_id, location, agent_id):
    name = f"projects/{project_id}/locations/{location}/reasoningEngines/{agent_id}"
    print(f"Deleting agent: {agent_id}...")
    client.agent_engines.delete(name=name, force=True)
    print("Agent deleted successfully.")


async def main():
    parser = argparse.ArgumentParser(description="Vertex AI Agent Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.required = True

    # Prompt command
    prompt_parser = subparsers.add_parser(
        "prompt", help="Send a prompt to a deployed agent"
    )
    prompt_parser.add_argument(
        "--agent-id",
        required=True,
        help="The ID of the deployed agent (e.g. your AGENT_RUNTIME_ID)",
    )
    prompt_parser.add_argument(
        "--message", required=True, help="The message/prompt to send"
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List all deployed agents")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a deployed agent")
    delete_parser.add_argument(
        "--agent-id", required=True, help="The ID of the deployed agent to delete"
    )

    args = parser.parse_args()

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION")

    if not project_id or not location:
        print(
            "Error: GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION must be set in your environment or .env file."
        )
        return

    # Initialize the Vertex AI client
    client = vertexai.Client(project=project_id, location=location)

    if args.command == "prompt":
        await prompt_agent(client, project_id, location, args.agent_id, args.message)
    elif args.command == "list":
        # list() and delete() are synchronous operations in the SDK
        list_agents(client)
    elif args.command == "delete":
        delete_agent(client, project_id, location, args.agent_id)


if __name__ == "__main__":
    asyncio.run(main())
