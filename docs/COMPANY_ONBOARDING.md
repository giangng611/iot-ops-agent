# Company Onboarding

This guide helps a company adapt IoT Ops Agent to its own IoT platform without
changing product source code or committing secrets.

## 1. Decide the Deployment Boundary

Recommended production boundary:

```text
Flask web service
  -> authenticated UI, chat, Telegram, OpenAI calls, MCP client

MCP server
  -> bearer authentication, rate limits, audit log
  -> read-only operational data tools

Company systems
  -> MongoDB, Loki, Grafana, Prometheus, and related observability APIs

App database
  -> MySQL or Postgres/Supabase for users, chats, prompts, and identities
```

The Flask service should never receive direct credentials for company MongoDB,
Loki, Grafana, or Prometheus. Put those credentials only in the MCP server
environment.

## 2. Prepare Company Credentials

Create read-only accounts or tokens for:

- company MongoDB or compatible operational database
- Grafana API or read-only Grafana username/password
- Loki and Prometheus access, usually through Grafana datasources
- app-owned MySQL or Postgres/Supabase database
- OpenAI API access
- Telegram bot token, only when Telegram is enabled

Use least privilege:

- read-only database roles for operational evidence
- allowlisted MongoDB namespaces through `COMPANY_MONGO_ALLOWED_NAMESPACES`
- per-caller MCP bearer keys through `MCP_API_KEYS_JSON`
- HTTPS-only public endpoints in production

## 3. Configure the Flask App

Copy the root template:

```bash
cp .env.example .env
```

Required values:

```env
FLASK_SECRET_KEY=replace_me
OPENAI_API_KEY=replace_me
ACCESS_CODE=replace_me
APP_DB_BACKEND=mysql
MYSQL_DB_URL=mysql+pymysql://user:password@mysql-host:3306/iot_ops_agent?charset=utf8mb4
COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=https://your-mcp-host/mcp
MCP_BEARER_KEY=replace_me
```

Optional local simulator telemetry:

```env
ENABLE_EMBEDDED_TELEMETRY=true
ENABLE_MONGODB=true
READ_TELEMETRY_FROM_MONGO=true
TELEMETRY_WRITE_BACKEND=mongodb
MONGODB_URI=mongodb://telemetry_user:password@mongo-host:27017/iot_ops_agent
```

## 4. Configure the MCP Server

Copy the MCP template:

```bash
cp mcp_server/.env.example mcp_server/.env
```

Required values:

```env
COMPANY_MONGODB_URI=mongodb://readonly_user:password@company-mongo-host:27017/?authSource=admin&directConnection=true
COMPANY_MONGO_ALLOWED_NAMESPACES=authorization.IDENTITY,datamgmt.CNT,datamgmt.CIN
MCP_API_KEYS_JSON={"caller-id":"sha256_hash_of_raw_key"}
```

Generate a caller key pair:

```bash
python -c "import secrets, hashlib; k=secrets.token_urlsafe(24); print('RAW_KEY='+k); print('HASH='+hashlib.sha256(k.encode()).hexdigest())"
```

Put `RAW_KEY` in the Flask `MCP_BEARER_KEY`. Put `HASH` in the MCP
`MCP_API_KEYS_JSON`.

Optional Grafana/Loki/Prometheus access:

```env
MCP_ENABLE_GRAFANA_TOOLS=true
GRAFANA_URL=https://your-grafana-host
GRAFANA_USERNAME=readonly_user
GRAFANA_PASSWORD=replace_me
GRAFANA_API_KEY=
GRAFANA_TIMEOUT_SECONDS=10
DEFAULT_LOKI_NAMESPACE=iot-platform
DEFAULT_K8S_NAMESPACE=iot-platform
```

## 5. Adapt Runbooks

Review these company-specific values before production use:

- `COMPANY_MONGO_ALLOWED_NAMESPACES`
- default Loki and Kubernetes namespaces
- MongoDB collection names and projections
- OneM2M resource mappings
- RabbitMQ, EMQX, Kubernetes, and observability metric names
- Telegram allowed user IDs and data-source grants

Prefer configuration changes first. Change code only when your platform uses a
different data model or operational workflow.

## 6. Verify Locally

Start MCP:

```bash
PORT=8000 MCP_SERVER_HOST=127.0.0.1 .venv/bin/python mcp_server/server.py
```

Start Flask:

```bash
.venv/bin/python app.py
```

Run focused tests:

```bash
.venv/bin/python -m unittest tests.test_ioa_v3_workflow -v
```

Manual checks:

- create a user with `ACCESS_CODE`
- select simulator mode and confirm local fallback behavior
- select company mode and confirm MCP tool evidence appears in traces
- run `/resources` with a known device ID
- run `/rabbitmq`, `/queue-trend`, `/emqx-dropped`, `/reconnect`, and `/k8s`
- confirm failures are explicit and do not silently present simulator data as
  company evidence

## 7. Production Checklist

- `.env` and `mcp_server/.env` are not committed
- operational database users are read-only
- MCP bearer keys are unique per caller
- public Flask and MCP endpoints use HTTPS
- `APP_DB_FALLBACK_ENABLED=false`
- log retention and audit requirements are defined
- secrets are stored in the hosting platform or secret manager
- any public fork has been scanned for secrets and private artifacts
