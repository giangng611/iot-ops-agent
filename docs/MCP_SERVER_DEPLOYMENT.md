# MCP Server Deployment

IoT Ops Agent public edition does not deploy MCP for you. Deploy an
MCP-compatible service supplied or implemented by your company, then point the
Flask app at it.

## Deployment Boundary

```text
IoT Ops Agent Flask app
  -> MCP_SERVER_URL + MCP_BEARER_KEY
  -> company-provided MCP server
  -> MongoDB / Loki / Grafana / Prometheus
```

The MCP server owns all operational credentials. The Flask app should never
receive direct MongoDB, Loki, Grafana, or Prometheus secrets.

## MCP Service Requirements

Your MCP deployment should provide:

- authenticated MCP endpoint, preferably HTTPS in production
- read-only operational tools
- per-caller bearer keys
- rate limits
- audit logs
- namespace/tool allowlists for database reads
- read-only credentials for operational systems

See [mcp_server/README.md](../mcp_server/README.md) for the contract.

## Flask Deployment Configuration

Configure the web service:

```env
COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=https://your-mcp-host/mcp
MCP_BEARER_KEY=replace_me
GRAFANA_TOOL_ACCESS_MODE=mcp
```

For Docker Compose:

```bash
MCP_SERVER_URL=https://your-mcp-host/mcp \
docker-compose --env-file /dev/null up --build
```

## Network Requirements

Deploy the MCP service somewhere that can reach company operational systems:

- company MongoDB or compatible operational database
- Grafana
- Loki/Prometheus datasources
- internal network/VPN resources required by those systems

If the MCP host cannot reach those systems, the Flask app should receive tool
errors or unavailable metadata, not raw credentials or internal stack traces.

## Rotation

1. Generate a new raw bearer key/hash pair.
2. Add the hash to the MCP server's `MCP_API_KEYS_JSON`.
3. Put the raw key into the Flask app's `MCP_BEARER_KEY`.
4. Redeploy/reload both services as needed.
5. Remove old hashes after callers migrate.

## Production Checklist

- [ ] MCP server is deployed from a source you have rights to use.
- [ ] Operational credentials are stored only on the MCP service.
- [ ] Database roles are read-only.
- [ ] `MCP_SERVER_URL` uses HTTPS outside local development.
- [ ] Each caller has a separate bearer key.
- [ ] Tool calls are audited.
- [ ] Database namespaces and tool parameters are allowlisted.
- [ ] Flask falls back explicitly when MCP is unavailable.
