# MCP Server Usage

The public edition does not include an MCP server implementation. The MCP
server used in the private deployment was supplied by an external/company
platform team.

Use this guide to connect IoT Ops Agent to a company-provided MCP-compatible
server.

## 1. Start Your MCP Server

Start the MCP service from your company's repository, package, or platform.
The service should expose an authenticated endpoint such as:

```text
http://127.0.0.1:8000/mcp
https://your-mcp-host/mcp
```

The expected server-side environment contract is documented in
[mcp_server/README.md](../mcp_server/README.md) and
[mcp_server/.env.example](../mcp_server/.env.example).

## 2. Generate a Caller Key Pair

The MCP service should store only SHA-256 hashes of raw bearer keys.

```bash
python -c "import secrets, hashlib; k=secrets.token_urlsafe(24); print('RAW_KEY='+k); print('HASH='+hashlib.sha256(k.encode()).hexdigest())"
```

- Put `RAW_KEY` in the Flask app as `MCP_BEARER_KEY`.
- Put `HASH` in your MCP server's `MCP_API_KEYS_JSON`.

## 3. Configure Flask

In the root `.env`:

```env
COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=http://127.0.0.1:8000/mcp
MCP_BEARER_KEY=replace_me
GRAFANA_TOOL_ACCESS_MODE=mcp
```

Start Flask:

```bash
.venv/bin/python app.py
```

## 4. Smoke Test

In the web UI:

1. Log in.
2. Select the company data source.
3. Run a read-only runbook such as `/resources`, `/rabbitmq`,
   `/emqx-dropped`, `/reconnect`, or `/k8s`.
4. Confirm the reasoning trace shows MCP-backed tool evidence.

If MCP is unavailable, the app should return explicit unavailable/fallback
metadata. It should not present simulator data as company evidence.

## 5. Expected Tool Families

The private deployment used tool names similar to:

```text
mongo_find
mongo_list_databases
mongo_list_collections
grafana_list_datasources
grafana_query
grafana_query_range
loki_query_range
```

Your MCP server can expose the same names, or you can adapt the Flask mapping
layer in `services/mcp_client.py`, `services/company_mongo_proxy.py`, and
`services/mcp_observability_service.py`.

## 6. Testing With MCP Inspector

If your MCP server supports streamable HTTP:

```bash
npx -y @modelcontextprotocol/inspector
```

Use:

```text
Transport Type: Streamable HTTP
URL: http://127.0.0.1:8000/mcp
Header: Authorization: Bearer <RAW_KEY>
```

Then list tools and run a harmless read-only call.
