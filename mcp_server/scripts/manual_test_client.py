"""Manual MCP client for smoke-testing mcp_server/.

Usage (works the same in bash, PowerShell, cmd.exe -- avoids shell quoting
issues with embedded JSON by accepting key=value pairs instead):
  python mcp_server/scripts/manual_test_client.py list
  python mcp_server/scripts/manual_test_client.py call mongo_find database=authorization collection=IDENTITY limit=5
  python mcp_server/scripts/manual_test_client.py call loki_query_range query={namespace="iot-platform"} start=0 end=100 limit=5

For tools that need nested JSON (e.g. a Mongo query filter), write the args
to a JSON file and pass it with @:
  python mcp_server/scripts/manual_test_client.py call mongo_find @args.json

Env vars:
  MCP_SERVER_URL      e.g. http://127.0.0.1:8000/mcp (defaults to that)
  MCP_TEST_BEARER_KEY raw bearer key to authenticate with
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _coerce_value(raw_value):
    try:
        return json.loads(raw_value)
    except ValueError:
        return raw_value


def parse_tool_args(argv_rest):
    if not argv_rest:
        return {}

    if len(argv_rest) == 1 and argv_rest[0].startswith("@"):
        file_path = argv_rest[0][1:]

        with open(file_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    if len(argv_rest) == 1 and argv_rest[0].strip().startswith("{"):
        return json.loads(argv_rest[0])

    args = {}

    for pair in argv_rest:
        if "=" not in pair:
            raise SystemExit(
                f"Expected key=value, got: {pair!r}. "
                "Use key=value pairs, a single JSON object, or @file.json."
            )

        key, raw_value = pair.split("=", 1)
        args[key] = _coerce_value(raw_value)

    return args


async def run(command, tool_name=None, tool_args=None):
    url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
    bearer_key = os.getenv("MCP_TEST_BEARER_KEY", "")
    headers = {"Authorization": f"Bearer {bearer_key}"} if bearer_key else {}

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            if command == "list":
                tools = await session.list_tools()
                for tool in tools.tools:
                    print(f"- {tool.name}: {tool.description}")
                return

            if command == "call":
                result = await session.call_tool(tool_name, tool_args or {})
                print("isError:", result.isError)
                print("content:")
                for item in result.content:
                    print(" ", getattr(item, "text", item))
                print("structuredContent:", json.dumps(result.structuredContent, default=str))
                return

            raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: manual_test_client.py list | call <tool_name> [key=value ...]"
        )

    command = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else None
    args = parse_tool_args(sys.argv[3:])

    asyncio.run(run(command, name, args))
