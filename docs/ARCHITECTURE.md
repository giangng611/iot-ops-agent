# Architecture

IoT Ops Agent is structured as a full-stack AI operations platform.

---

## High-Level Flow

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

## Core Components

## 1. Telemetry Simulator

`simulator.py` generates virtual telemetry for 10 IoT devices.

Each device produces:

- CPU usage
- memory usage
- heartbeat delay
- status
- log message
- alarm metadata

Statuses are computed from operational thresholds:

```text
CPU warning: >= 75%
Memory warning: >= 80%
Heartbeat warning: >= 180s

CPU critical: >= 90%
Memory critical: >= 90%
Heartbeat critical: >= 600s
```

---

## 2. SQLite Database

`database.py` stores:

- telemetry records
- users
- chats
- messages
- reasoning traces

Main tables include:

```text
telemetry
users
chats
messages
```

---

## 3. Flask Backend

`app.py` provides:

- dashboard routes
- authentication routes
- telemetry APIs
- chat persistence APIs
- profile APIs
- streaming diagnosis endpoint
- WebSocket broadcasting

---

## 4. WebSocket Layer

Flask-SocketIO broadcasts realtime updates to the frontend.

The dashboard receives:

```text
device_update
```

and updates:

- device table
- fleet charts
- alert center

---

## 5. Agent Layer

The project includes two agent modes.

### IOA v1

Single-step tool-calling assistant.

Flow:

```text
User query
→ select one tool
→ call tool
→ generate final answer
```

### IOA v2

Multi-step reasoning agent.

Flow:

```text
User query
→ Thought
→ Action
→ Observation
→ Repeat
→ Final Answer
```

The reasoning trace is streamed to the frontend in realtime.

---

## 6. Frontend UI

The frontend uses:

- HTML
- CSS
- Vanilla JavaScript
- Chart.js
- Socket.IO client

Main UI areas:

- Home chat workspace
- Devices tab
- Alerts tab
- Prompts tab
- Profile tab
- Reasoning drawer
- Device history modal

---

## Context-Aware Agent Behavior

The agent tracks the latest target device.

Example:

```text
User: diagnose gateway-003
Agent: diagnoses gateway-003

User: check its alarms
Agent: understands "its" = gateway-003
```

---

## Reasoning Trace Streaming

The backend streams intermediate reasoning events:

```text
thought
observation
final
error
```

The frontend renders these events in the right-side reasoning drawer.