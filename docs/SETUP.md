# Setup Guide

This guide explains how to run IoT Ops Agent locally.

---

## 1. Clone Repository

```bash id="w19q0h"
git clone https://github.com/giangng611/iot-ops-agent.git
cd iot-ops-agent
```

---

## 2. Install Dependencies

```bash id="bvv7fr"
pip install -r requirements.txt
```

---

## 3. Configure Environment Variables

Create a `.env` file in the project root:

```env id="zwkz1x"
OPENAI_API_KEY=your_openai_api_key_here
FLASK_SECRET_KEY=your_flask_secret_key_here
ACCESS_CODE=your_access_code_here
```

### Generate a Flask Secret Key

```bash id="jq96ww"
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Do not commit `.env` to GitHub.

Environment variables are required for:

* OpenAI API access
* session management
* protected account registration

---

## 4. Initialize Database

```bash id="sq1gmb"
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

```bash id="hq29oj"
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

```bash id="mnjjzn"
python3 app.py
```

Open the application:

```text id="6ng7pn"
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

## Common Issues

### Database table not found

Run:

```bash id="af1n9q"
python3 init_db.py
```

Make sure the command is executed from the project root.

---

### Environment variables not loading

Verify that `.env` exists in the project root and includes:

```env id="s6m8mg"
OPENAI_API_KEY=...
FLASK_SECRET_KEY=...
ACCESS_CODE=...
```

Restart the Flask application after updating environment variables.

---

### WebSocket not connected

Open browser DevTools and check the console for realtime connection logs.

Expected behavior:

```text id="7axn5r"
Connected to realtime device stream.
```

---

### OpenAI API authentication failed

Verify that:

```env id="lzpk2v"
OPENAI_API_KEY=your_real_api_key
```

is correctly configured inside `.env`.

If the API key is invalid, the AI workspace will return authentication errors.

---

## Optional Deployment

The application can also be deployed to Render.

Recommended environment variables for deployment:

```env id="aqsl3s"
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
