# IoT Ops Agent

AI-powered IoT observability platform with realtime telemetry simulation, multi-step reasoning agents, streaming diagnostics, and fleet analytics.

---

<p align="center">
  <img src="screenshots/demo.png" width="1000">
</p>

## Overview

IoT Ops Agent is a simulated IoT operations platform that monitors virtual devices, streams telemetry updates, detects warning and critical conditions, and uses LLM-powered agents to diagnose infrastructure issues.

The project compares two agent modes:

- **IOA v1** — single-step tool-calling assistant
- **IOA v2** — multi-step reasoning agent with streaming ReAct-style diagnostics

---

## Key Features

- Multi-step AI diagnostics with reasoning traces
- Realtime WebSocket device updates
- SQLite-backed telemetry, users, chats, and reasoning history
- Fleet-level health and alert dashboards
- Device-level historical telemetry charts
- Local authentication and user-specific chat history
- Searchable, pinnable, and persistent chat sidebar

---

## Screenshots

### Dashboard Home

<p align="center">
  <img src="screenshots/dashboard.png" width="1000">
</p>

### Streaming Reasoning Trace

<p align="center">
  <img src="screenshots/reasoning-trace.png" width="1000">
</p>

### Devices Tab

<p align="center">
  <img src="screenshots/devices-tab.png" width="1000">
</p>

### Device Telemetry History

<p align="center">
  <img src="screenshots/telemetry-history.png" width="1000">
</p>

### Alerts Dashboard

<p align="center">
  <img src="screenshots/alerts-tab.png" width="1000">
</p>

### Profile & Settings

<p align="center">
  <img src="screenshots/profile-tab.png" width="1000">
</p>

### Authentication Screen

<p align="center">
  <img src="screenshots/login-screen.png" width="1000">
</p>

### Prompt Library

<p align="center">
  <img src="screenshots/prompts-tab.png" width="1000">
</p>

---

## Architecture

```text
Simulated IoT Devices
          ↓
Telemetry Simulator
          ↓
SQLite Database
          ↓
Flask Backend API
          ↓
AI Agent Layer
          ↓
Realtime Dashboard UI
```

---

## Tech Stack

**Backend**
- Python
- Flask
- Flask-SocketIO
- SQLite
- OpenAI API

**Frontend**
- HTML
- CSS
- Vanilla JavaScript
- Chart.js

**AI**
- ReAct-style reasoning loop
- Tool-calling agents
- Streaming reasoning traces
- Context-aware diagnostics

---

## Quick Start

```bash
git clone https://github.com/giangng611/iot-ops-agent.git
cd iot-ops-agent

pip install -r requirements.txt

python3 init_db.py
python3 simulator.py
python3 app.py
```

Open:

```text
http://127.0.0.1:5001
```

---

## Documentation

- [Setup Guide](docs/SETUP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Features](docs/FEATURES.md)
- [Roadmap](docs/ROADMAP.md)

---

## Author

Giang Nguyen Do  
Computer Science @ University of Georgia