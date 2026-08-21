# Bring Your Own MCP Server

The public edition of IoT Ops Agent does not include an MCP server
implementation.

The MCP implementation used in the original private deployment was supplied by
an external/company platform team. To keep this public repository clean and
reusable, this folder contains only the integration contract. Each company
should provide, deploy, or adapt its own MCP-compatible server.

## What the Flask App Expects

The Flask app calls a remote MCP endpoint configured by:

```env
COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=https://your-mcp-host/mcp
MCP_BEARER_KEY=replace_me
GRAFANA_TOOL_ACCESS_MODE=mcp
```

The MCP server should:

- accept authenticated MCP requests over HTTP/SSE or streamable HTTP
- reject unauthenticated calls before touching operational systems
- expose only read-only tools for operational evidence
- enforce per-caller rate limits
- keep audit logs for tool calls
- own all direct MongoDB, Grafana, Loki, and Prometheus credentials

## Required Tool Families

The app is designed around these MCP-backed evidence families:

- MongoDB or platform database reads for OneM2M/device operational evidence
- Grafana datasource discovery
- Prometheus instant/range queries through Grafana or a compatible adapter
- Loki log range queries

The public app code calls MCP through `services/mcp_client.py`. The IOA v3
runtime expects tool responses to be JSON-serializable dictionaries or lists,
with explicit unavailable/error payloads instead of leaked raw exceptions.

## Common Tool Names

The private deployment used tool names like these. Your MCP server can expose
the same names, or you can adapt the mapping layer in the Flask app:

```text
mongo_find
mongo_list_databases
mongo_list_collections
grafana_list_datasources
grafana_query
grafana_query_range
loki_query_range
```

For the higher-level IOA v3 runbooks, the app may also call service-layer
wrappers that ultimately reach MCP-backed MongoDB, Loki, Grafana, and
Prometheus evidence.

## MCP Server Environment Contract

Use `.env.example` in this folder as a checklist for your own MCP service.
Do not commit the real `.env`.

Minimum auth/data contract:

```env
COMPANY_MONGODB_URI=replace_me
COMPANY_MONGO_ALLOWED_NAMESPACES=authorization.IDENTITY,datamgmt.CNT,datamgmt.CIN
MCP_API_KEYS_JSON={"caller-id":"sha256_hash_of_raw_key"}
```

Optional observability contract:

```env
MCP_ENABLE_GRAFANA_TOOLS=true
GRAFANA_URL=https://your-grafana-host
GRAFANA_USERNAME=readonly_user
GRAFANA_PASSWORD=replace_me
GRAFANA_API_KEY=
DEFAULT_LOKI_NAMESPACE=iot-platform
DEFAULT_K8S_NAMESPACE=iot-platform
```

Generate a caller key pair:

```bash
python -c "import secrets, hashlib; k=secrets.token_urlsafe(24); print('RAW_KEY='+k); print('HASH='+hashlib.sha256(k.encode()).hexdigest())"
```

Put `RAW_KEY` in the Flask app as `MCP_BEARER_KEY`. Put only `HASH` in the MCP
server's `MCP_API_KEYS_JSON`.

## Local Usage

1. Start your company-provided MCP server separately.
2. Confirm it is reachable from the Flask app host.
3. Configure the Flask `.env`:

```env
COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=http://127.0.0.1:8000/mcp
MCP_BEARER_KEY=replace_me
```

4. Start Flask:

```bash
.venv/bin/python app.py
```

5. In the UI, select the company data source and run a read-only runbook such
   as `/resources`, `/rabbitmq`, `/emqx-dropped`, `/reconnect`, or `/k8s`.

If MCP is unavailable, the app should show explicit unavailable/fallback
metadata. It should not present simulator data as company evidence.

## Docker Usage

The public `docker-compose.yml` runs only the web app. Point it at your
external MCP server:

```bash
MCP_SERVER_URL=http://host.docker.internal:8000/mcp \
docker-compose --env-file /dev/null up --build
```

For a remote MCP service:

```bash
MCP_SERVER_URL=https://your-mcp-host/mcp \
docker-compose --env-file /dev/null up --build
```

## Security Notes

- Keep operational credentials only in your MCP service.
- Use read-only database users.
- Use allowlists for database namespaces and tool parameters.
- Use one bearer key per caller.
- Use HTTPS in production.
- Rotate keys that were ever exposed.
