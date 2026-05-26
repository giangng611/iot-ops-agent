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
```

Generate a Flask secret key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Do not commit `.env` to GitHub.

---

## 4. Initialize Database

```bash
python3 init_db.py
```

This creates the required SQLite tables for:

- telemetry
- users
- chats
- messages

---

## 5. Start Telemetry Simulator

Open a terminal and run:

```bash
python3 simulator.py
```

The simulator continuously generates telemetry for 10 virtual IoT devices.

---

## 6. Start Flask App

Open another terminal and run:

```bash
python3 app.py
```

Open the app:

```text
http://127.0.0.1:5001
```

---

## 7. Login

On first launch:

1. Create a local account.
2. Log in.
3. Access the dashboard.

---

## Common Issues

### Database table not found

Run:

```bash
python3 init_db.py
```

Make sure you run this command from the project root.

---

### Environment variables not loading

Check that `.env` exists in the project root and includes:

```env
OPENAI_API_KEY=...
FLASK_SECRET_KEY=...
```

---

### WebSocket not connected

Open browser DevTools and check the console for:

```text
Connected to realtime device stream.
```