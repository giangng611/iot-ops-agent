# IoT Ops Agent

IoT Ops Agent is an AI-powered operations workspace for enterprise IoT
platforms. It combines a Flask + Socket.IO web app, authenticated chat
workflows, simulator fallback, and an MCP server that gates access to
operational evidence such as MongoDB, Loki, Grafana, and Prometheus.

This repository is the public product-template edition. It is designed so a
company can clone the code, keep its own credentials in environment files or
deployment secrets, and adapt the allowed data namespaces/runbooks to its IoT
platform.

## Architecture

```text
Web UI / Telegram
  -> Flask app / IOA runtimes
  -> MCP server
  -> Company MongoDB / Loki / Grafana / Prometheus

App-owned data
  -> MySQL or Postgres/Supabase

Simulator telemetry
  -> MongoDB when enabled
  -> SQLite only as local fallback/debug storage
```

The Flask app must not hold company MongoDB, Loki, Grafana, or Prometheus
credentials. Those secrets belong to the MCP server. Flask only receives
`MCP_SERVER_URL` and `MCP_BEARER_KEY`.

## Features

- AI-assisted IoT operations diagnosis
- streamed reasoning traces and tool evidence
- authenticated users, chats, prompts, and Telegram identities
- source-aware simulator/company execution
- MCP-gated read-only operational evidence
- OneM2M command, telemetry, and resource checks
- RabbitMQ backlog and queue-growth checks
- EMQX dropped-message and reconnect checks
- Kubernetes resource checks
- Docker Compose packaging for web + MCP services

## Quick Start

```bash
git clone <repo-url>
cd iot-ops-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create app config:

```bash
cp .env.example .env
```

Configure at minimum:

```env
FLASK_SECRET_KEY=replace_me
OPENAI_API_KEY=replace_me
ACCESS_CODE=replace_me

APP_DB_BACKEND=mysql
APP_DB_FALLBACK_ENABLED=false
MYSQL_DB_URL=mysql+pymysql://user:password@127.0.0.1:3306/iot_ops_agent?charset=utf8mb4

COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=http://127.0.0.1:8000/mcp
MCP_BEARER_KEY=replace_me
```

Create MCP config:

```bash
cp mcp_server/.env.example mcp_server/.env
```

Configure at minimum:

```env
COMPANY_MONGODB_URI=mongodb://readonly_user:password@company-mongo-host:27017/?authSource=admin&directConnection=true
MCP_API_KEYS_JSON={"caller-id":"sha256_hash_of_raw_key"}
```

Start MCP server in one terminal:

```bash
PORT=8000 MCP_SERVER_HOST=127.0.0.1 .venv/bin/python mcp_server/server.py
```

Start Flask in another terminal:

```bash
.venv/bin/python app.py
```

Open:

```text
http://127.0.0.1:5001
```

See [Setup](docs/SETUP.md) and
[Company Onboarding](docs/COMPANY_ONBOARDING.md) for the full environment
contract.

## Docker Quick Start

For a containerized Flask/MCP runtime that uses `.env` and
`mcp_server/.env`:

```bash
docker-compose --env-file /dev/null up --build
```

Open:

```text
http://127.0.0.1:5001
```

The Compose file intentionally does not start production MySQL, company
MongoDB, Grafana, Loki, or Prometheus. It packages the app services and
connects them to the external systems configured by each deployment.

If you prefer an isolated local MySQL container:

```bash
docker-compose --env-file /dev/null \
  -f docker-compose.yml \
  -f docker-compose.local-db.yml \
  up --build
```

## Operational Runbooks

Implemented MCP-backed runbooks:

- Command Downlink Debug
- Telemetry Uplink Debug
- Device Resource Check
- RabbitMQ Top Backlog
- RabbitMQ Queue Trend
- EMQX Dropped Messages
- EMQX Connect/Disconnect
- Kubernetes Resource Check

Prompt aliases are available in the chat input:

```text
/cmd
/telemetry
/resources
/rabbitmq
/queue-trend
/emqx-dropped
/reconnect
/k8s
```

## Public Template Notes

- Do not commit `.env`, `mcp_server/.env`, database dumps, reports, backups, or
  generated evidence artifacts.
- Use read-only database users for operational data.
- Store deployment secrets in GitHub Actions secrets, hosting-provider secrets,
  Docker/Kubernetes secrets, or the target server environment.
- Treat `COMPANY_MONGO_ALLOWED_NAMESPACES` and observability namespaces as
  company-specific configuration.
- Rotate any key that was ever committed, pasted into logs, or shared outside
  the intended deployment.

## Documentation

- [Company Onboarding](docs/COMPANY_ONBOARDING.md)
- [Public Release Checklist](docs/PUBLIC_RELEASE_CHECKLIST.md)
- [Setup](docs/SETUP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Features](docs/FEATURES.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Security](docs/SECURITY.md)
- [IOA v3 Ops Graph](docs/IOA_V3_LANGGRAPH_N8N_GRAFANA.md)
- [OneM2M Operational Scenarios](docs/ONEM2M_OPERATIONAL_SCENARIOS.md)
- [MCP Server Integration](docs/MCP_SERVER_INTEGRATION.md)
- [MCP Server Usage](docs/MCP_SERVER_USAGE.md)
- [MCP Server Deployment](docs/MCP_SERVER_DEPLOYMENT.md)
- [Benchmarking](docs/BENCHMARKING.md)
- [Telegram PoC](docs/TELEGRAM_POC.md)
- [LangGraph Governance](docs/LANGGRAPH_GOVERNANCE.md)

## Verification

Run focused IOA v3 workflow tests:

```bash
.venv/bin/python -m unittest tests.test_ioa_v3_workflow -v
```

Run the full backend suite:

```bash
.venv/bin/python -m unittest discover -s tests
```

Check app storage health:

```bash
.venv/bin/python -m scripts.check_app_storage_status
```

## License

MIT License © 2026 Giang Nguyen Do
