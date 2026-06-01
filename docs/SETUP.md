# Setup Guide

This guide explains how to run IoT Ops Agent locally.

---

## 1. Clone Repository

```bash
git clone https://github.com/giangng611/iot-ops-agent.git
cd iot-ops-agent
```

---

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

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
ACCESS_CODE=your_access_code_here
N8N_WEBHOOK_URL=http://localhost:5678/webhook/iot-ops-eval
DIFY_API_URL=http://localhost/v1/chat-messages
DIFY_API_KEY=your_dify_app_api_key_here
DIFY_USER=iot-ops-agent-ui
```

### Generate a Flask Secret Key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Do not commit `.env` to GitHub.

Environment variables are required for:

* OpenAI API access
* session management
* Socket.IO origin checks
* diagnosis request size and rate limits
* protected account registration
* optional n8n runtime testing through the UI
* optional Dify runtime testing through the UI

---

## 4. Initialize Database

```bash
python3 init_db.py
```

This creates the required SQLite tables for:

* telemetry
* users
* chats
* messages
* prompts

---

## 5. Start Telemetry Simulator

Open a terminal and run:

```bash
python3 simulator.py
```

The simulator continuously generates telemetry for 10 virtual IoT devices.

Generated telemetry includes:

* CPU usage
* memory usage
* heartbeat delay
* operational status
* alarms
* alert severity
* log messages

---

## 6. Start Flask Application

Open another terminal and run:

```bash
python3 app.py
```

Open the application:

```text
http://127.0.0.1:5001
```

---

## 7. Create Account & Login

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

## 8. Realtime Dashboard Behavior

Once the simulator and Flask app are running:

* telemetry streams into the dashboard
* fleet charts update automatically
* alerts appear in realtime
* SocketIO pushes live device updates
* AI diagnostics can analyze operational conditions

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

Dify should return a structured operational diagnosis and a UI-visible reasoning trace. Local testing showed at least three reasoning iterations per Dify execution.

---

## Common Issues

### Database table not found

Run:

```bash
python3 init_db.py
```

Make sure the command is executed from the project root.

---

### Environment variables not loading

Verify that `.env` exists in the project root and includes:

```env
OPENAI_API_KEY=...
FLASK_SECRET_KEY=...
ACCESS_CODE=...
DIFY_API_KEY=...
```

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
* SQLite
* Render hosting
* environment-based configuration
