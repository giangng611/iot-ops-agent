import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402
import uvicorn  # noqa: E402

from mcp_server.auth import BearerAuthMiddleware  # noqa: E402
from mcp_server.tools.mongo_tools import register_mongo_tools  # noqa: E402

load_dotenv(os.path.join(MCP_SERVER_DIR, ".env"))

mcp = FastMCP("iot-ops-mcp-server", stateless_http=True)

register_mongo_tools(mcp)

# Loki and Grafana/Prometheus both go through the same Grafana datasource
# proxy (mcp_server/services/grafana_session.py), just a different
# datasource id -- so they're gated behind the same flag.
if os.getenv("MCP_ENABLE_GRAFANA_TOOLS", "false").lower() == "true":
    from mcp_server.tools.grafana_tools import register_grafana_tools
    from mcp_server.tools.loki_tools import register_loki_tools

    register_loki_tools(mcp)
    register_grafana_tools(mcp)


def build_app():
    app = mcp.streamable_http_app()
    return BearerAuthMiddleware(app)


def main():
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("MCP_SERVER_PORT", "8000")))
    uvicorn.run(build_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
