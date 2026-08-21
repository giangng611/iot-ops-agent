# MCP Server Integration Reference

This public repository treats MCP as an external integration boundary. It does
not include the private/company MCP implementation.

## Architecture

```text
Flask app / IOA runtimes
  -- Authorization: Bearer <RAW_KEY> -->
Company-provided MCP server
  -> read-only MongoDB or operational database tools
  -> Loki log tools
  -> Grafana/Prometheus metric tools
```

Only the MCP server should hold operational credentials:

- `COMPANY_MONGODB_URI`
- `GRAFANA_URL`
- `GRAFANA_USERNAME`
- `GRAFANA_PASSWORD`
- `GRAFANA_API_KEY`

The Flask app only needs:

- `MCP_SERVER_URL`
- `MCP_BEARER_KEY`

## Connection

```text
URL:        https://your-mcp-host/mcp
Transport:  streamable HTTP or compatible MCP transport
Header:     Authorization: Bearer <RAW_KEY>
```

Unauthenticated requests should be rejected before any operational system is
read.

## Expected Tool Families

The app expects read-only evidence from these families:

| Family | Purpose |
|---|---|
| MongoDB/platform database reads | OneM2M resources, device inventory, telemetry/resource evidence |
| Grafana datasource discovery | Resolve datasource UIDs for metrics/logs |
| Prometheus/Grafana queries | RabbitMQ, EMQX, Kubernetes, infrastructure metrics |
| Loki log queries | service logs, trace/device keyword searches |

Common tool names used by the private integration:

```text
mongo_find
mongo_list_databases
mongo_list_collections
grafana_list_datasources
grafana_query
grafana_query_range
loki_query_range
```

If your MCP server uses different names or schemas, adapt:

- `services/mcp_client.py`
- `services/company_mongo_proxy.py`
- `services/mcp_observability_service.py`
- IOA v3 tool mapping in `agents/ioa_v3_agent.py`

## Response Contract

Tool responses should be JSON-serializable and safe to display in reasoning
traces.

Recommended response behavior:

- return structured dictionaries/lists for successful reads
- return explicit unavailable/error payloads for upstream failures
- redact credentials and internal connection strings
- distinguish `not found`, `empty result`, and `tool unavailable`
- include enough source metadata for auditability

## Server-Side Environment Contract

Use [mcp_server/.env.example](../mcp_server/.env.example) as a checklist for
your MCP service.

Important variables:

| Var | Purpose |
|---|---|
| `COMPANY_MONGODB_URI` | read-only operational database connection |
| `COMPANY_MONGO_ALLOWED_NAMESPACES` | allowed `db.collection` reads |
| `MCP_API_KEYS_JSON` | `caller_id -> sha256(raw_key)` auth map |
| `MCP_RATE_LIMIT_REQUESTS` / `MCP_RATE_LIMIT_WINDOW_SECONDS` | caller rate limits |
| `MCP_ENABLE_GRAFANA_TOOLS` | enable observability tools |
| `GRAFANA_URL` / `GRAFANA_*` | Grafana/Loki/Prometheus access |
| `DEFAULT_LOKI_NAMESPACE` | default log namespace |
| `DEFAULT_K8S_NAMESPACE` | default Kubernetes namespace |

## Security Expectations

- Use read-only operational credentials.
- Enforce authentication before tool dispatch.
- Use one bearer key per caller.
- Enforce allowlists for database reads.
- Log tool calls without logging raw secrets.
- Use HTTPS in production.
