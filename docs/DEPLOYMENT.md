# Deployment Guide

This guide explains how to deploy IoT Ops Agent using Render.

---

## Current Deployment

Live Demo:

```text id="k2y6q7"
https://iot-ops-agent.onrender.com
```

Current deployment stack:

* Flask
* Flask-SocketIO
* SQLite
* Render Web Service
* environment-variable based configuration

---

## 1. Push Project to GitHub

Create a GitHub repository and push the project:

```bash id="4e8vra"
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

```text id="fz2b2d"
https://render.com
```

Create a new:

```text id="0r6uzg"
Web Service
```

Connect the GitHub repository.

---

## 3. Configure Render Settings

### Build Command

```bash id="r7m2vl"
pip install -r requirements.txt
```

### Start Command

```bash id="m8vpx3"
python3 app.py
```

### Runtime

```text id="p88l4u"
Python 3
```

---

## 4. Configure Environment Variables

Inside the Render dashboard, add:

```env id="r2hivk"
OPENAI_API_KEY=your_openai_api_key
FLASK_SECRET_KEY=your_secret_key
ACCESS_CODE=your_access_code
```

These variables are required for:

* OpenAI API access
* Flask session security
* protected account registration

Do not commit secrets into GitHub.

---

## 5. Deploy Application

Click:

```text id="7e6w2y"
Deploy Web Service
```

Render will:

1. install dependencies
2. build the application
3. launch the Flask server
4. generate a public deployment URL

---

## 6. Initialize Database

On first deployment, the SQLite database must be initialized.

You can initialize the database by:

### Option A — Local Initialization

Run locally before deployment:

```bash id="9gg5l7"
python3 init_db.py
```

Then commit the generated SQLite database file.

---

### Option B — Startup Initialization

Alternatively, initialize the database automatically inside `app.py`:

```python id="9dtj6t"
init_db()
```

before starting the Flask application.

---

## 7. Start Telemetry Simulator

The simulator continuously generates realtime device telemetry.

Run:

```bash id="n1e2dr"
python3 simulator.py
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

### SQLite Limitation

SQLite works well for demos and lightweight deployments, but is not ideal for large-scale production systems.

Future production deployments should migrate to:

```text id="vxwp6o"
PostgreSQL
```

---

### Free Render Limitation

On the free Render plan:

* services may sleep after inactivity
* cold starts may occur
* realtime streams may reconnect after wake-up

This behavior is expected for free-tier deployments.

---

## 11. Recommended Future Production Stack

```text id="egwq0j"
Flask + Gunicorn
        ↓
PostgreSQL
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

```env id="u8qyrz"
OPENAI_API_KEY=...
```

inside Render environment variables.

---

### Users Cannot Register

Verify:

```env id="mc0r9l"
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

Verify the telemetry simulator is running and inserting telemetry into the database.

---

## 13. Production Improvement Ideas

Potential future deployment improvements:

* Docker containerization
* Supabase/PostgreSQL migration
* MQTT ingestion
* distributed telemetry workers
* centralized logging
* admin dashboard
* external alert delivery
* cloud object storage
