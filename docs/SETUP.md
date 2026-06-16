# Setup Guide

This guide explains how to run IoT Ops Agent locally.

---

## 1. Clone Repository

```bash
git clone https://github.com/giangng611/iot-ops-agent.git
cd iot-ops-agent
```

---

## 2. Create a Python Environment

Python 3.11 or 3.12 is recommended. Create and activate a project-local
virtual environment before installing dependencies.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks the activation script, use Command Prompt:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows commonly uses `py` or `python`, while macOS commonly uses `python3`
to create the environment. After activation, the remaining commands in this
guide use `python` on every operating system.

---

## 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key_here
FLASK_SECRET_KEY=your_flask_secret_key_here
SOCKETIO_CORS_ORIGINS=
MAX_DIAGNOSE_MESSAGE_CHARS=2000
DIAGNOSE_RATE_LIMIT_REQUESTS=10
DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS=60
ENABLE_EMBEDDED_TELEMETRY=true
TELEMETRY_BROADCAST_INTERVAL_SECONDS=300
ENABLE_MONGODB=false
READ_TELEMETRY_FROM_MONGO=false
TELEMETRY_WRITE_BACKEND=sqlite
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=iot_ops_agent
MONGODB_TELEMETRY_COLLECTION=telemetry
APP_DB_BACKEND=supabase
APP_DB_FALLBACK_ENABLED=false
SUPABASE_DB_URL=postgresql://postgres.project-ref:password@region.pooler.supabase.com:6543/postgres
POSTGRES_POOL_MIN_SIZE=1
POSTGRES_POOL_MAX_SIZE=5
POSTGRES_POOL_TIMEOUT_SECONDS=5
POSTGRES_CONNECT_TIMEOUT_SECONDS=5
POSTGRES_STATEMENT_TIMEOUT_MS=4000
POSTGRES_LOCK_TIMEOUT_MS=3000
POSTGRES_CIRCUIT_BREAKER_SECONDS=30
APP_TIMEZONE=Asia/Ho_Chi_Minh
ACCESS_CODE=your_access_code_here
N8N_WEBHOOK_URL=http://localhost:5678/webhook/iot-ops-eval
DIFY_API_URL=http://localhost/v1/chat-messages
DIFY_API_KEY=your_dify_app_api_key_here
DIFY_USER=iot-ops-agent-ui
PUBLIC_BASE_URL=http://127.0.0.1:5001
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_UPDATE_RETENTION_SECONDS=86400
TELEGRAM_DEFAULT_DATA_SOURCE=simulator
TELEGRAM_LINK_CODE_TTL_MINUTES=15
COMPANY_MONGODB_URI=
COMPANY_MONGODB_DB=
COMPANY_DB_CONNECT_TIMEOUT_SECONDS=5
COMPANY_DB_STATEMENT_TIMEOUT_MS=5000
COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS=120
COMPANY_MONGO_PROXY_RATE_LIMIT_WINDOW_SECONDS=60
```

### Generate a Flask Secret Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Do not commit `.env` to GitHub.

Environment variables are required for:

* OpenAI API access
* session management
* Socket.IO origin checks
* diagnosis request size and rate limits
* embedded demo telemetry generation
* optional MongoDB telemetry dual-write
* optional MongoDB telemetry read path
* telemetry write backend selection
* optional Supabase/Postgres app-data migration and fallback policy
* protected account registration
* optional n8n runtime testing through the UI
* optional Dify runtime testing through the UI

---

## 4. Initialize Database

```bash
python init_db.py
```

This creates the required SQLite tables for:

* telemetry
* users
* chats
* messages
* prompts

---

## 5. Start Telemetry

The default `ENABLE_EMBEDDED_TELEMETRY=true` setting makes Flask generate
simulator telemetry before each Socket.IO broadcast. A second process is not
required.

To use the standalone simulator, change:

```env
ENABLE_EMBEDDED_TELEMETRY=false
```

Then open another terminal and run:

```bash
python simulator.py
```

The standalone simulator continuously generates telemetry for 10 virtual IoT
devices.

Generated telemetry includes:

* CPU usage
* memory usage
* heartbeat delay
* operational status
* alarms
* alert severity
* log messages

### Optional: Enable MongoDB Telemetry Dual-Write

Phase A keeps SQLite as the primary database and writes a copy of each
generated telemetry record to MongoDB only when MongoDB is enabled.

```env
ENABLE_MONGODB=true
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=iot_ops_agent
MONGODB_TELEMETRY_COLLECTION=telemetry
```

After MongoDB is running and the simulator has inserted at least one batch,
verify the MongoDB copy:

```bash
python -m scripts.check_mongodb_telemetry --limit 5
```

The output should show a non-zero `count` and recent telemetry documents.

Telemetry write backend options:

```env
TELEMETRY_WRITE_BACKEND=sqlite   # legacy/default, write telemetry to SQLite
TELEMETRY_WRITE_BACKEND=dual     # write telemetry to SQLite and MongoDB
TELEMETRY_WRITE_BACKEND=mongodb  # write new telemetry only to MongoDB
```

Verify the active write backend:

```bash
python -m scripts.check_telemetry_write_backend
```

When `TELEMETRY_WRITE_BACKEND=mongodb`, the SQLite telemetry count should stay
unchanged and the MongoDB telemetry count should increase by the generated
batch size.

### Optional: Check MongoDB Read APIs

Phase B adds read-only MongoDB telemetry APIs while keeping the existing
SQLite dashboard and agent context unchanged.

```bash
python -m scripts.check_mongodb_api --device-id sensor-001 --limit 5
```

The script checks:

* `GET /api/mongo/telemetry/health`
* `GET /api/mongo/devices`
* `GET /api/mongo/telemetry/<device_id>`

These endpoints require an authenticated session in the Flask app. The check
script creates a local test session for verification.

### Optional: Read Telemetry From MongoDB

Phase C allows existing telemetry consumers to read from MongoDB while keeping
SQLite as the fallback.

```env
ENABLE_MONGODB=true
READ_TELEMETRY_FROM_MONGO=true
TELEMETRY_WRITE_BACKEND=mongodb
```

When enabled, the existing app routes and agent context use MongoDB for:

* latest device list
* device telemetry history
* latest device status
* system overview and alarm tools

SQLite remains the fallback if MongoDB is unavailable or returns no telemetry.
Existing API responses include a `source` field so the active read source is
visible during testing.

Verify the active read source:

```bash
python -m scripts.check_telemetry_read_source
```

### Optional: Prepare MongoDB Telemetry Indexes

Phase D adds MongoDB indexes for the telemetry read path.

```bash
python -m scripts.ensure_mongodb_indexes
```

The script creates or verifies:

* `device_timestamp_desc` for latest status and per-device history
* `timestamp_desc` for latest telemetry checks
* `status_timestamp_desc` for status-based alert queries

You can also inspect indexes through the authenticated Flask API:

```text
GET /api/mongo/telemetry/indexes
POST /api/mongo/telemetry/indexes
```

### Optional: Backfill SQLite Telemetry to MongoDB

After MongoDB dual-write and read-source checks are working, you can migrate
existing SQLite telemetry rows into MongoDB.

Preview the number of SQLite telemetry rows:

```bash
python -m scripts.backfill_sqlite_telemetry_to_mongodb --dry-run
```

Run the backfill:

```bash
python -m scripts.backfill_sqlite_telemetry_to_mongodb --batch-size 500
```

The backfill is idempotent. It stores migrated rows with:

* `source=sqlite_backfill`
* `sqlite_id=<original SQLite telemetry id>`

MongoDB also has a partial unique index on `(source, sqlite_id)` for
`source=sqlite_backfill`, so running the backfill again will not duplicate
migrated SQLite rows.

---

## 6. Optional: Migrate App Data to Supabase/Postgres

Telemetry remains in MongoDB. Supabase/Postgres is only for relational app data:

* users
* chats
* messages
* prompts

Create a Supabase project, open **Project Settings -> Database -> Connect**,
and copy a Postgres connection string. For local backend/server scripts on
IPv4 networks, the Transaction Pooler connection string is usually the
simplest starting point.

Add it to `.env`:

```env
APP_DB_BACKEND=supabase
APP_DB_FALLBACK_ENABLED=false
SUPABASE_DB_URL=postgresql://postgres.project-ref:password@region.pooler.supabase.com:6543/postgres
POSTGRES_POOL_MIN_SIZE=1
POSTGRES_POOL_MAX_SIZE=5
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Check the connection:

```bash
python -m scripts.check_supabase_postgres
```

Apply the app-data schema:

```bash
python -m scripts.apply_supabase_schema
```

Preview SQLite app-data counts:

```bash
python -m scripts.migrate_sqlite_app_data_to_supabase
```

Run the migration:

```bash
python -m scripts.migrate_sqlite_app_data_to_supabase --apply
```

This migration preserves integer IDs so existing chat/message/prompt
relationships remain stable. Switch the Flask app-data runtime after migration:

```env
APP_DB_BACKEND=supabase
```

After switching app data to Supabase/Postgres, verify the active app-data
backend and telemetry source:

```bash
python -m scripts.check_app_storage_status
```

Verify migrated app-data integrity:

```bash
python -m scripts.verify_supabase_app_data_migration
```

When `APP_DB_BACKEND=supabase`, the app writes users, chats, messages, prompts,
Telegram identities, and Telegram link codes to Supabase/Postgres.

Keep silent SQLite fallback disabled when Supabase is the source of truth:

```env
APP_DB_BACKEND=supabase
APP_DB_FALLBACK_ENABLED=false
```

With fallback disabled, Supabase/Postgres connection failures return backend
errors instead of writing new app data to SQLite. This avoids split-brain app
data when Supabase is expected to be the source of truth.

The schema migrations enable Row Level Security and revoke direct table access
from the Supabase `anon` and `authenticated` roles. The Flask server continues
to use its direct Postgres connection; browser-side Data API access is denied
by default. Verify the deployed security state with:

```bash
python -m scripts.check_supabase_rls
```

If browser-side Supabase access is added later, design per-user policies and
explicitly grant only the required operations before exposing a publishable
key.

---

## 7. Start Flask Application

Open another terminal and run:

```bash
python app.py
```

Open the application:

```text
http://127.0.0.1:5001
```

---

## 8. Create Account & Login

On first launch:

1. Open the login page.
2. Create a local account using the configured access code.
3. Log in to access the dashboard.

The platform supports:

* persistent sessions
* local authentication
* password hashing
* protected workspace access

---

## 9. Realtime Dashboard Behavior

Once the simulator and Flask app are running:

* telemetry streams into the dashboard
* fleet charts update automatically
* alerts appear in realtime
* SocketIO pushes live device updates
* AI diagnostics can analyze operational conditions

---

## Optional Company DB Source

Configure a read-only Company MongoDB account:

```env
COMPANY_MONGODB_URI=mongodb://readonly_user:password@company-host:27017/?authSource=admin
COMPANY_DB_CONNECT_TIMEOUT_SECONDS=5
COMPANY_DB_STATEMENT_TIMEOUT_MS=5000
COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS=120
COMPANY_MONGO_PROXY_RATE_LIMIT_WINDOW_SECONDS=60
```

Start Flask from a machine that can reach the company network, then select
`Company DB` in the Profile runtime drawer. The UI reports
`company_mongodb` when active and `simulator_fallback` when the read fails.

Probe the schema without exposing unrestricted database access:

```bash
python -m scripts.probe_company_db --table-limit 20
```

See [Company DB Discovery](COMPANY_DB_DISCOVERY.md) for the bounded read model,
proxy restrictions, and provisional PoC rules.

---

## Optional Dify Runtime Setup

The `IOA v2 · Dify` runtime is optional. It is used for local runtime comparison and self-hosted chatbot-style agent testing.

### 1. Start Dify Locally

Clone the Dify repository with a shallow clone to avoid downloading the full Git history:

```bash
cd ~/Desktop
git clone --depth 1 https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker-compose up -d
```

If Docker Desktop is not installed, this project has also been tested locally with Homebrew Docker CLI plus Colima:

```bash
brew install colima docker docker-compose
colima start --cpu 4 --memory 8 --disk 60
cd ~/Desktop/dify/docker
docker-compose up -d
```

Open Dify:

```text
http://127.0.0.1/install
```

### 2. Create a Dify App

In Dify:

1. Create an admin account.
2. Choose `Create from Blank`.
3. Select `Chatflow`.
4. Name the app `IoT Ops Agent Eval`.
5. Keep the simple flow shape: `Start -> LLM -> Answer`.
6. Configure an LLM provider such as OpenAI.
7. Publish the app.
8. Open `API Access` and create an app API key.

Suggested LLM instruction:

```text
You are an IoT operations assistant.

Use only the operational context provided by the caller.
Do not invent device IDs, telemetry values, alarms, or logs.
Answer in this format:
Summary:
Evidence:
Likely Cause:
Suggested Next Action:
```

### 3. Configure IoT Ops Agent

Add the Dify app key to this project `.env`:

```env
DIFY_API_URL=http://localhost/v1/chat-messages
DIFY_API_KEY=app-your_dify_app_api_key
DIFY_USER=iot-ops-agent-ui
```

Restart Flask after updating `.env`.

### 4. Test Dify From the UI

Open the IoT Ops Agent UI and select:

```text
IOA v2 · Dify
```

Then run:

```text
/overview system health
```

Dify should return a structured operational diagnosis and a UI-visible
app-level trace when the configured Chatflow returns steps. Trace length
depends on the Dify workflow and must not be treated as proof of tool use.

---

## Common Issues

### Database table not found

Run:

```bash
python init_db.py
```

Make sure the command is executed from the project root.

---

### Environment variables not loading

Verify that `.env` exists in the project root and includes:

```env
OPENAI_API_KEY=...
FLASK_SECRET_KEY=...
ACCESS_CODE=...
```

`DIFY_API_KEY` is required only when using the Dify runtime.

Restart the Flask application after updating environment variables.

### Dify API key is not configured

If the UI returns:

```text
DIFY_API_KEY is not configured.
```

verify that `.env` includes:

```env
DIFY_API_URL=http://localhost/v1/chat-messages
DIFY_API_KEY=app-your_dify_app_api_key
DIFY_USER=iot-ops-agent-ui
```

Then restart Flask. Environment variables are loaded only when the Flask process starts.

---

### WebSocket not connected

Open browser DevTools and check the console for realtime connection logs.

Expected behavior:

```text
Connected to realtime device stream.
```

---

### OpenAI API authentication failed

Verify that:

```env
OPENAI_API_KEY=your_real_api_key
```

is correctly configured inside `.env`.

If the API key is invalid, the AI workspace will return authentication errors.

---

## Optional Deployment

The application can also be deployed to Render.

Recommended environment variables for deployment:

```env
OPENAI_API_KEY=...
FLASK_SECRET_KEY=...
ACCESS_CODE=...
```

The current deployment architecture uses:

* Flask
* Flask-SocketIO
* MongoDB for telemetry when enabled
* Supabase/Postgres for app data when enabled
* SQLite legacy/fallback storage
* Render hosting
* environment-based configuration
