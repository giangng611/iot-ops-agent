# Security

IoT Ops Agent is designed around a strict separation between the web app and
operational credentials.

## Secret Handling

- Never commit `.env` or `mcp_server/.env`.
- Keep real OpenAI, Telegram, database, MCP, and Grafana credentials in a secret
  manager or deployment environment.
- Commit only `.env.example` files with placeholders.
- Rotate any key that was committed, pasted into an issue, shared in logs, or
  exposed in a public artifact.

## Operational Data Boundary

The Flask app is an MCP client. It should not receive direct credentials for
company MongoDB, Loki, Grafana, or Prometheus.

The MCP server owns:

- read-only operational database credentials
- Grafana/Loki/Prometheus credentials
- per-caller bearer-key verification through `MCP_API_KEYS_JSON`
- rate limiting and audit logging
- allowed MongoDB namespace enforcement

## Recommended Production Controls

- Use HTTPS for public Flask and MCP endpoints.
- Use read-only operational database users.
- Use one MCP bearer key per caller and rotate keys regularly.
- Keep `APP_DB_FALLBACK_ENABLED=false` for production.
- Restrict Telegram access with `TELEGRAM_ALLOWED_USER_IDS` and user grants.
- Review `COMPANY_MONGO_ALLOWED_NAMESPACES` before enabling company mode.
- Keep generated reports, evidence exports, screenshots, and database dumps out
  of public repositories.

## Reporting Issues

If you find a security issue in your deployment, rotate affected credentials
first, preserve the relevant audit logs, and then patch the deployment.
