# Setup

This guide describes the company-oriented local setup. The normal stack is:

- Flask app for UI, auth, chat, prompts, Telegram, and agent execution
- MySQL for app data after migration from Supabase/Postgres
- MCP server for company MongoDB, Loki, Grafana, and Prometheus evidence
- MongoDB for optional simulator telemetry storage
- SQLite only as fallback/debug storage, not as the expected runtime database

## 1. Python Environment

Use Python 3.11 or 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Flask App Environment

Create `.env` in the repository root. Keep app-owned credentials here only.

```env
FLASK_SECRET_KEY=replace_me
APP_TIMEZONE=Asia/Ho_Chi_Minh
PUBLIC_BASE_URL=http://127.0.0.1:5001
ACCESS_CODE=replace_me
SOCKETIO_CORS_ORIGINS=

OPENAI_API_KEY=replace_me

APP_DB_BACKEND=supabase
APP_DB_FALLBACK_ENABLED=false
SUPABASE_DB_URL=replace_me
POSTGRES_POOL_MIN_SIZE=1
POSTGRES_POOL_MAX_SIZE=5
POSTGRES_POOL_TIMEOUT_SECONDS=5
POSTGRES_CONNECT_TIMEOUT_SECONDS=5
POSTGRES_STATEMENT_TIMEOUT_MS=4000
POSTGRES_LOCK_TIMEOUT_MS=3000
POSTGRES_CIRCUIT_BREAKER_SECONDS=30

# Fill these before migration. Switch APP_DB_BACKEND=mysql only after verify passes.
MYSQL_DB_URL=mysql+pymysql://user:password@127.0.0.1:3306/iot_ops_agent?charset=utf8mb4
MYSQL_CONNECT_TIMEOUT_SECONDS=5
MYSQL_READ_TIMEOUT_SECONDS=5
MYSQL_WRITE_TIMEOUT_SECONDS=5

COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=http://127.0.0.1:8000/mcp
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

TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_DEFAULT_DATA_SOURCE=company
TELEGRAM_LINK_CODE_TTL_MINUTES=15

N8N_WEBHOOK_URL=
DIFY_API_URL=
DIFY_API_KEY=
DIFY_USER=iot-ops-agent-ui
```

Do not put company MongoDB, Loki, Grafana, or Prometheus credentials in the
Flask `.env`. The Flask app is an MCP client only.

Generate a Flask secret when needed:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 3. App Data: Supabase to MySQL

App data means:

- users
- chats
- messages
- prompts
- Telegram identities
- Telegram link codes
- per-user data-source policy

MongoDB, Loki, Grafana, and Prometheus are not part of this migration. They
stay behind MCP.

### Current Source: Supabase/Postgres

Keep Supabase configured while exporting data:

```bash
.venv/bin/python scripts/apply_supabase_schema.py
.venv/bin/python scripts/check_app_storage_status.py
```

```env
APP_DB_BACKEND=supabase
APP_DB_FALLBACK_ENABLED=false
SUPABASE_DB_URL=replace_me
```

### Target: Local MySQL

Create the database first. Then apply the app schema:

```bash
.venv/bin/python scripts/apply_mysql_schema.py
```

Migrate and verify:

```bash
.venv/bin/python scripts/migrate_postgres_app_data_to_mysql.py
.venv/bin/python scripts/migrate_postgres_app_data_to_mysql.py --apply
.venv/bin/python scripts/verify_mysql_app_data_migration.py
```

After verification passes, switch the app:

```env
APP_DB_BACKEND=mysql
APP_DB_FALLBACK_ENABLED=false
MYSQL_DB_URL=mysql+pymysql://user:password@127.0.0.1:3306/iot_ops_agent?charset=utf8mb4
```

Keep fail-closed behavior in company/runtime setups. The app must not silently
create production chat/user data in SQLite.

## 4. MCP Server Environment

Create `mcp_server/.env`. This file owns company operational credentials.

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

Use either Grafana username/password or an API key, depending on the company
deployment. Do not commit this file.

Start MCP:

```bash
PORT=8000 MCP_SERVER_HOST=127.0.0.1 .venv/bin/python mcp_server/server.py
```

Expected unauthenticated browser checks against `/` may return `401`. That is
normal; MCP clients must use the bearer key.

## 5. Simulator Telemetry

Simulator telemetry is useful for local UI checks and fallback behavior.

Recommended simulator storage:

```env
ENABLE_EMBEDDED_TELEMETRY=true
ENABLE_MONGODB=true
READ_TELEMETRY_FROM_MONGO=true
TELEMETRY_WRITE_BACKEND=mongodb
```

SQLite fallback is only for degraded local/debug cases:

```env
TELEMETRY_WRITE_BACKEND=sqlite
READ_TELEMETRY_FROM_MONGO=false
```

Verify simulator MongoDB storage when enabled:

```bash
.venv/bin/python -m scripts.check_mongodb_telemetry --limit 5
.venv/bin/python -m scripts.check_telemetry_read_source
```

## 6. Start Flask

Run Flask in a second terminal while MCP is running:

```bash
.venv/bin/python app.py
```

Open:

```text
http://127.0.0.1:5001
```

Create an account with `ACCESS_CODE`, then choose the company data source for
MCP-backed runbooks.

## 7. Telegram

Telegram stays in the Flask app because it is user/channel integration, not
company operational evidence.

Required variables when enabled:

```env
TELEGRAM_BOT_TOKEN=replace_me
TELEGRAM_WEBHOOK_SECRET=replace_me
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_DEFAULT_DATA_SOURCE=company
PUBLIC_BASE_URL=https://your-public-url
```

Configure webhook:

```bash
.venv/bin/python scripts/configure_telegram_webhook.py
```

## 8. Runbook Verification

Run the focused IOA v3 tests:

```bash
.venv/bin/python -m unittest tests.test_ioa_v3_workflow -v
```

Manual runbook aliases:

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

If metric workflows return no samples, verify the metric name, label set, MCP
Grafana datasource, and Prometheus scrape target before assigning root cause.
