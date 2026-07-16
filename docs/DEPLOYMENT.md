# Deployment

This guide describes the company-oriented deployment shape. The app and MCP
server are separate services with separate secrets.

## Target Services

```text
Flask web service
  - Web UI
  - Socket.IO
  - auth/session handling
  - chats, prompts, Telegram integration
  - OpenAI/LLM calls
  - MCP client only

MCP server
  - bearer auth
  - rate limits and audit log
  - company MongoDB read proxy
  - Loki queries
  - Grafana/Prometheus queries

MySQL
  - app-owned relational data after Supabase/Postgres migration

MongoDB
  - optional simulator telemetry storage
  - company MongoDB is reached only by MCP
```

SQLite exists only as fallback/debug storage and should not be the expected
production app-data backend.

## Flask Environment

Configure these on the Flask web service:

```env
FLASK_SECRET_KEY=replace_me
APP_TIMEZONE=Asia/Ho_Chi_Minh
PUBLIC_BASE_URL=https://your-app-host
ACCESS_CODE=replace_me
SOCKETIO_CORS_ORIGINS=https://your-app-host

OPENAI_API_KEY=replace_me

APP_DB_BACKEND=mysql
APP_DB_FALLBACK_ENABLED=false
SUPABASE_DB_URL=
POSTGRES_POOL_MIN_SIZE=1
POSTGRES_POOL_MAX_SIZE=5
POSTGRES_POOL_TIMEOUT_SECONDS=5
POSTGRES_CONNECT_TIMEOUT_SECONDS=5
POSTGRES_STATEMENT_TIMEOUT_MS=4000
POSTGRES_LOCK_TIMEOUT_MS=3000
POSTGRES_CIRCUIT_BREAKER_SECONDS=30
MYSQL_DB_URL=mysql+pymysql://user:password@mysql-host:3306/iot_ops_agent?charset=utf8mb4
MYSQL_CONNECT_TIMEOUT_SECONDS=5
MYSQL_READ_TIMEOUT_SECONDS=5
MYSQL_WRITE_TIMEOUT_SECONDS=5

COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=https://your-mcp-host/mcp
MCP_BEARER_KEY=replace_me
GRAFANA_TOOL_ACCESS_MODE=mcp
IOA_V3_ENABLE_KPI_RULES=false
IOA_V3_SEMANTIC_PLANNER_ENABLED=true

ENABLE_EMBEDDED_TELEMETRY=true
ENABLE_MONGODB=true
READ_TELEMETRY_FROM_MONGO=true
TELEMETRY_WRITE_BACKEND=mongodb
MONGODB_URI=replace_me
MONGODB_DB=iot_ops_agent
MONGODB_TELEMETRY_COLLECTION=telemetry
```

Optional Telegram:

```env
TELEGRAM_BOT_TOKEN=replace_me
TELEGRAM_WEBHOOK_SECRET=replace_me
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_DEFAULT_DATA_SOURCE=company
TELEGRAM_LINK_CODE_TTL_MINUTES=15
```

Optional runtimes:

```env
N8N_WEBHOOK_URL=
DIFY_API_URL=
DIFY_API_KEY=
DIFY_USER=iot-ops-agent-ui
```

Do not configure company MongoDB, Loki, Grafana, or Prometheus credentials on
the Flask service.

## MCP Environment

Configure these on the MCP service:

```env
COMPANY_MONGODB_URI=replace_me
COMPANY_MONGO_ALLOWED_NAMESPACES=authorization.IDENTITY,subNNotif.AE,subNNotif.SUB,datamgmt.CNT,datamgmt.CIN,datamgmt.DEVICE_TELEMETRY,datamgmt.RULE,devicemgmt.NODE,orchestration.URI_MAPPER

MCP_API_KEYS_JSON={"caller-id":"sha256_hash_of_raw_key"}
MCP_RATE_LIMIT_REQUESTS=60
MCP_RATE_LIMIT_WINDOW_SECONDS=60

MCP_ENABLE_GRAFANA_TOOLS=true
GRAFANA_URL=replace_me
GRAFANA_USERNAME=
GRAFANA_PASSWORD=
GRAFANA_API_KEY=
LOKI_URL=
```

Use one raw bearer key per caller and store only its SHA-256 hash in
`MCP_API_KEYS_JSON`.

Start command:

```bash
PORT=8000 MCP_SERVER_HOST=0.0.0.0 .venv/bin/python mcp_server/server.py
```

## App Data Migration

Use Supabase/Postgres only as the source during migration. MySQL is the target
runtime database.

On local or a controlled migration host:

```bash
.venv/bin/python scripts/apply_mysql_schema.py
.venv/bin/python scripts/migrate_postgres_app_data_to_mysql.py
.venv/bin/python scripts/migrate_postgres_app_data_to_mysql.py --apply
.venv/bin/python scripts/verify_mysql_app_data_migration.py
.venv/bin/python scripts/check_app_storage_status.py
```

Fail closed in deployment:

```env
APP_DB_BACKEND=mysql
APP_DB_FALLBACK_ENABLED=false
```

This prevents split-brain app data during MySQL outages. Do not enable SQLite
fallback for company/runtime deployments.

## Simulator Telemetry MongoDB

When simulator telemetry is enabled, prefer MongoDB:

```bash
.venv/bin/python -m scripts.ensure_mongodb_indexes
.venv/bin/python -m scripts.check_mongodb_telemetry --limit 5
```

SQLite fallback files must not be committed or treated as production storage.

## Flask Start Command

```bash
.venv/bin/python app.py
```

The app listens on `PORT` when the hosting platform provides it.

## Telegram Webhook

After the Flask service has a public URL:

```bash
.venv/bin/python scripts/configure_telegram_webhook.py
```

Operators must link their Telegram account to an IoT Ops Agent user before
Telegram-originated runbooks can access the company data source.

## Verification

Run these after deployment:

```bash
.venv/bin/python -m scripts.check_app_storage_status
.venv/bin/python -m unittest tests.test_ioa_v3_workflow -v
```

Manual platform checks:

- login and create a chat
- select company data source
- run `/resources` with a known device ID
- run `/rabbitmq`, `/emqx-dropped`, `/reconnect`, and `/k8s`
- confirm reasoning trace observations show MCP tool execution
- confirm fallback is explicit if MCP or company evidence is unavailable

## Security Notes

- keep `.env` and `mcp_server/.env` out of Git
- rotate MCP bearer keys per caller
- keep company credentials only on MCP
- keep Supabase credentials only during migration, then remove them from runtime
- keep `APP_DB_FALLBACK_ENABLED=false` for company/runtime deployments
- use HTTPS for public Flask and MCP endpoints
