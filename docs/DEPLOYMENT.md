# Deployment Guide

This guide explains how to deploy IoT Ops Agent using Render.

---

## Current Deployment

Live Demo:

```text
https://iot-ops-agent.onrender.com
```

Current deployment stack:

* Flask
* Flask-SocketIO
* MongoDB telemetry storage when enabled
* Supabase/Postgres app-data storage when enabled
* SQLite legacy/fallback storage
* Render Web Service
* environment-variable based configuration

---

## 1. Push Project to GitHub

Create a GitHub repository and push the project:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY
git push -u origin main
```

---

## 2. Create Render Web Service

Go to:

```text
https://render.com
```

Create a new:

```text
Web Service
```

Connect the GitHub repository.

---

## 3. Configure Render Settings

### Build Command

```bash
pip install -r requirements.txt
```

### Start Command

```bash
python app.py
```

### Runtime

```text
Python 3
```

---

## 4. Configure Environment Variables

Inside the Render dashboard, add the required variables:

```env
OPENAI_API_KEY=your_openai_api_key
FLASK_SECRET_KEY=your_secret_key
SOCKETIO_CORS_ORIGINS=https://iot-ops-agent.onrender.com
MAX_DIAGNOSE_MESSAGE_CHARS=2000
DIAGNOSE_RATE_LIMIT_REQUESTS=10
DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS=60
ENABLE_EMBEDDED_TELEMETRY=true
TELEMETRY_BROADCAST_INTERVAL_SECONDS=300
ENABLE_MONGODB=true
READ_TELEMETRY_FROM_MONGO=true
TELEMETRY_WRITE_BACKEND=mongodb
MONGODB_URI=your_mongodb_uri
MONGODB_DB=iot_ops_agent
MONGODB_TELEMETRY_COLLECTION=telemetry
APP_DB_BACKEND=supabase
APP_DB_FALLBACK_ENABLED=false
SUPABASE_DB_URL=your_supabase_transaction_pooler_url
POSTGRES_POOL_MIN_SIZE=1
POSTGRES_POOL_MAX_SIZE=5
APP_TIMEZONE=Asia/Ho_Chi_Minh
ACCESS_CODE=your_access_code
```

Add `N8N_WEBHOOK_URL` only when the deployed service can reach an n8n
webhook. A localhost webhook is not reachable from a separate Render service.

Add these only if the deployed app should call a reachable Dify instance:

```env
DIFY_API_URL=https://your-dify-host/v1/chat-messages
DIFY_API_KEY=your_dify_app_api_key
DIFY_USER=iot-ops-agent-ui
```

These variables are required for:

* OpenAI API access
* Flask session security
* Socket.IO origin checks
* diagnosis request size and rate limits
* embedded demo telemetry generation
* MongoDB telemetry storage
* Supabase/Postgres app-data storage
* app-data fallback policy
* protected account registration

Optional Dify variables are required only for `IOA v2 · Dify`.

Optional Telegram variables:

```env
PUBLIC_BASE_URL=https://iot-ops-agent.onrender.com
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_DEFAULT_DATA_SOURCE=simulator
TELEGRAM_LINK_CODE_TTL_MINUTES=15
```

Telegram access requires users to link their Telegram account to an IoT Ops
Agent account. The normal flow is Profile -> Telegram -> Generate Link Code,
then send `/link CODE` to the bot. Admin bootstrap remains available through
`python -m scripts.upsert_telegram_identity`. Grant `company` in
`--data-sources` only to operators approved to query Company DB through
Telegram.

Company MongoDB variables should be configured only when the Render service
can reach the company network:

```env
COMPANY_MONGODB_URI=...
COMPANY_DB_CONNECT_TIMEOUT_SECONDS=5
COMPANY_DB_STATEMENT_TIMEOUT_MS=5000
COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS=120
COMPANY_MONGO_PROXY_RATE_LIMIT_WINDOW_SECONDS=60
```

Do not commit secrets into GitHub.

For hosted production deployments, `DIFY_API_URL` should point to a reachable Dify instance. A local URL such as `http://localhost/v1/chat-messages` only works when Dify runs on the same host as Flask.

---

## 5. Deploy Application

Click:

```text
Deploy Web Service
```

Render will:

1. install dependencies
2. build the application
3. launch the Flask server
4. generate a public deployment URL

---

## 6. Initialize Storage

SQLite fallback tables are initialized automatically by `app.py` through
`init_db()`. For production-like deployments, initialize external storage before
switching traffic to it.

Apply Supabase/Postgres app-data schema:

```bash
python -m scripts.apply_supabase_schema
```

If you are migrating existing local app data:

```bash
python -m scripts.migrate_sqlite_app_data_to_supabase --apply
python -m scripts.verify_supabase_app_data_migration
```

Prepare MongoDB telemetry indexes:

```bash
python -m scripts.ensure_mongodb_indexes
```

Do not commit generated local SQLite database files for production
deployments. Keep `.env`, database files, and secrets out of Git.

---

## 7. Realtime Telemetry

For the hosted Render demo, keep embedded telemetry enabled:

```env
ENABLE_EMBEDDED_TELEMETRY=true
TELEMETRY_BROADCAST_INTERVAL_SECONDS=300
```

This lets the Flask web service generate a fresh telemetry batch before each
Socket.IO broadcast, so the dashboard remains connected even without a separate
background worker.

For local development, you can either use embedded telemetry or disable it and
run the standalone simulator:

```env
ENABLE_EMBEDDED_TELEMETRY=false
```

```bash
python simulator.py
```

The simulator powers:

* fleet dashboards
* alerts
* telemetry charts
* realtime device updates
* AI operational diagnosis

---

## 8. Realtime Features

The deployed platform supports:

* realtime SocketIO updates
* streaming AI responses
* reasoning trace streaming
* operational alert updates
* telemetry synchronization

---

## 9. Authentication System

The platform includes:

* local login
* protected registration
* access-code gated account creation
* password hashing
* session persistence
* protected routes

Only users with the configured `ACCESS_CODE` can create accounts.

---

## 10. Important Deployment Notes

### Storage Model

Production-like deployments should use external storage:

```text
MongoDB for telemetry
Supabase/Postgres for app data
SQLite only for explicit legacy/local demos
```

Set `APP_DB_FALLBACK_ENABLED=false` when Supabase/Postgres should be the source
of truth. With fallback disabled, app-data connection failures return backend
errors instead of silently writing new rows to SQLite.

Supabase RLS is enabled for all app-data tables, with direct access revoked
from the `anon` and `authenticated` roles. Run
`python -m scripts.check_supabase_rls` after applying migrations. If
browser-side Supabase clients are added, define per-user policies and grant
only the required operations before exposing publishable keys.

---

### Free Render Limitation

On the free Render plan:

* services may sleep after inactivity
* cold starts may occur
* realtime streams may reconnect after wake-up

This behavior is expected for free-tier deployments.

---

## 11. Recommended Future Production Stack

```text
Flask + Gunicorn
        ↓
Supabase/Postgres app data
        ↓
MongoDB telemetry
        ↓
Redis Queue / Workers
        ↓
Cloud Infrastructure
        ↓
Custom Domain + HTTPS
```

---

## 12. Troubleshooting

### Invalid OpenAI API Key

Verify:

```env
OPENAI_API_KEY=...
```

inside Render environment variables.

---

### Users Cannot Register

Verify:

```env
ACCESS_CODE=...
```

matches the access code entered during signup.

---

### WebSocket Not Updating

Check:

* Flask-SocketIO installation
* Render logs
* browser console
* simulator status

---

### Devices Not Appearing

Verify the telemetry simulator is running and inserting telemetry into the
configured telemetry backend.

For MongoDB telemetry mode, verify:

```bash
python -m scripts.check_mongodb_telemetry --limit 5
python -m scripts.check_app_storage_status
```

---

## 13. Production Improvement Ideas

Potential future deployment improvements:

* Docker containerization
* MQTT ingestion
* distributed telemetry workers
* centralized logging
* admin dashboard
* external alert delivery
* cloud object storage
