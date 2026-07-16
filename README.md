# IoT Ops Agent

AI-powered IoT operations workspace for company IoT platform triage. The app
keeps user/chat state in a relational app database, uses MCP as the gateway to
company operational evidence, and supports simulator fallback for local
resilience testing. The current migration path moves app data from
Supabase/Postgres to MySQL.

## Overview

IoT Ops Agent combines:

- Flask + Socket.IO web workspace
- authenticated users, chats, messages, prompts, and Telegram identities
- MySQL app-data storage after Supabase/Postgres migration
- MCP-backed access to company MongoDB, Loki, Grafana, and Prometheus
- IOA v3 Ops Graph runbooks for OneM2M, RabbitMQ, EMQX, and Kubernetes checks
- optional simulator telemetry for fallback and local verification

The intended production boundary is:

```text
Web UI / Telegram
  -> Flask app / IOA runtimes
  -> MCP server
  -> Company MongoDB / Loki / Grafana / Prometheus

App data
  -> MySQL after Supabase/Postgres migration

Simulator telemetry
  -> MongoDB when enabled
  -> SQLite only as last-resort fallback/debug storage
```

Flask must not hold company MongoDB, Loki, Grafana, or Prometheus credentials.
Those credentials belong in `mcp_server/.env`. Flask only receives
`MCP_SERVER_URL` and `MCP_BEARER_KEY`.

## Core Features

- AI-assisted operations diagnosis
- streamed reasoning traces
- source-aware company/simulator execution
- persistent chats and prompt workflows
- authenticated web workspace
- Telegram webhook integration
- relational app-data persistence
- MCP-gated read-only operational evidence
- OneM2M command, telemetry, and resource checks
- RabbitMQ backlog and queue-growth checks
- EMQX dropped-message and reconnect checks
- Kubernetes resource checks
- runtime benchmarking across the supported agent modes

## Runtime Modes

- `IOA v1 · Custom Python`
- `IOA v2 · Custom Python`
- `IOA v2 · LangChain`
- `IOA v2 · LangGraph`
- `IOA v2 · n8n`
- `IOA v2 · Dify`
- `IOA v3 · Ops Graph`

`IOA v3 · Ops Graph` is the controlled operational runtime for company
runbooks. It uses LangGraph policy/routing and MCP tools for bounded MongoDB,
Loki, Grafana, and Prometheus evidence.

## Quick Start

```bash
git clone <repo-url>
cd iot-ops-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create `.env` from [.env.example](.env.example), then configure at minimum:

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

See [Setup](docs/SETUP.md) for the full environment contract.

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

See [OneM2M Operational Scenarios](docs/ONEM2M_OPERATIONAL_SCENARIOS.md).

## Documentation

- [Setup](docs/SETUP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Features](docs/FEATURES.md)
- [Deployment](docs/DEPLOYMENT.md)
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

MIT License © 2026 
Giang Nguyen Do
