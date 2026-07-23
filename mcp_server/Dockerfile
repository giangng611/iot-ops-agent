# mcp_server/ is a fully independent service from the iot-ops-agent Flask
# app in the rest of this repo -- it has its own deploy target, its own env,
# and (mcp_server/services/company_mongo_proxy.py) its own vendored copy of
# the Mongo guardrail, so it does NOT import anything from outside this
# directory. Build context is mcp_server/ ITSELF, not the repo root:
#
#   docker build -t iot-ops-mcp-server mcp_server/
#   docker run -p 8000:8000 --env-file mcp_server/.env iot-ops-mcp-server
#
# See docs/MCP_SERVER_INTEGRATION.md for the env vars this service needs
# (COMPANY_MONGODB_URI, MCP_API_KEYS_JSON, GRAFANA_*, ...).

FROM python:3.11-slim

WORKDIR /app

# Install deps first (separate layer) so code-only changes don't bust the
# pip install cache.
COPY requirements.txt mcp_server/requirements.txt
RUN pip install --no-cache-dir -r mcp_server/requirements.txt

# Everything mcp_server/ needs lives under mcp_server/ itself.
COPY . mcp_server/

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# All real config (COMPANY_MONGODB_URI, MCP_API_KEYS_JSON, GRAFANA_*, ...) is
# injected at runtime via env vars / --env-file, never baked into the image.
CMD ["sh", "mcp_server/docker_entrypoint.sh"]
