# Architecture

IoT Ops Agent is structured as a full-stack AI operations platform that combines realtime telemetry simulation, AI-assisted diagnostics, operational alert management, and persistent user workspaces.

---

## High-Level Flow

```text
Simulated IoT Devices
          ↓
Telemetry Simulator
          ↓
SQLite Database
          ↓
Flask + SocketIO Backend
          ↓
AI Agent Layer
          ↓
Realtime Dashboard UI
```

---

## Core Components

## 1. Telemetry Simulator

`simulator.py` continuously generates telemetry for a simulated fleet of IoT devices.

Each device produces:

* CPU usage
* memory usage
* heartbeat delay
* operational status
* log messages
* alarm metadata
* alert severity

Operational status is computed from telemetry thresholds.

### Warning Thresholds

```text
CPU usage >= 75%
Memory usage >= 80%
Heartbeat delay >= 180s
```

### Critical Thresholds

```text
CPU usage >= 90%
Memory usage >= 90%
Heartbeat delay >= 600s
```

The simulator continuously inserts telemetry into the database, which powers realtime dashboards, alerts, telemetry charts, and AI diagnosis workflows.

---

## 2. SQLite Database

`database.py` manages persistent application storage.

The database stores:

* telemetry records
* users
* chats
* messages
* prompts
* reasoning traces

Main tables include:

```text
telemetry
users
chats
messages
prompts
```

The database layer also handles:

* authentication
* password hashing
* session-linked chat persistence
* prompt CRUD operations
* telemetry history queries
* profile management

---

## 3. Flask Backend

`app.py` acts as the main backend orchestration layer.

The backend provides:

* dashboard routes
* authentication APIs
* telemetry APIs
* prompt APIs
* profile APIs
* chat persistence APIs
* realtime streaming endpoints
* WebSocket broadcasting

The backend also coordinates:

* OpenAI API calls
* reasoning trace streaming
* alert generation
* telemetry retrieval
* frontend synchronization

---

## 4. WebSocket Layer

Flask-SocketIO enables realtime communication between the backend and frontend dashboard.

The frontend receives events such as:

```text
device_update
```

Realtime events update:

* device tables
* fleet health charts
* operational alerts
* dashboard statistics
* telemetry history views

The WebSocket layer allows the dashboard to update without requiring page refreshes.

---

## 5. Agent Layer

The platform includes multiple operational AI runtimes behind the same chat UI.

### IOA v1

Single-step tool-calling assistant.

Flow:

```text
User Query
→ Tool Selection
→ Tool Execution
→ Final Response
```

IOA v1 performs direct operational diagnosis with a simplified reasoning process.

---

### IOA v2

Multi-step reasoning agent using a ReAct-style workflow.

Flow:

```text
User Query
→ Thought
→ Action
→ Observation
→ Repeat
→ Final Answer
```

IOA v2 supports:

* iterative reasoning
* multi-step diagnosis
* operational context tracking
* streamed reasoning traces
* persistent reasoning history

Reasoning events are streamed to the frontend in realtime through the reasoning drawer.

---

### Framework Runtime Modes

The Home workspace can route the same user prompt and telemetry context through several runtime implementations:

* `IOA v2 · Custom Python`
* `IOA v2 · LangChain`
* `IOA v2 · LangGraph`
* `IOA v2 · n8n`
* `IOA v2 · Dify`

The external runtimes use Flask as the operational context packager. Flask collects:

* latest device telemetry
* fleet health overview
* active alarms
* target device status when applicable
* target device telemetry history when applicable

n8n receives this context through a webhook payload. Dify receives the same context through the Dify Chat Messages API using app inputs plus a composed LLM prompt.

### Dify Runtime Flow

```text
User Query
→ Flask /api/diagnose-stream
→ Build operational context
→ Dify Chat Messages API
→ Dify Chatflow LLM node
→ Structured response + steps
→ Flask SSE reasoning events
→ UI reasoning drawer
```

Dify is used as a self-hosted app runtime. It provides fast chatflow setup, model/provider configuration, app API keys, and a chatbot-oriented interface while keeping operational telemetry inside the IoT Ops Agent backend.

---

## 6. Frontend UI

The frontend is built using:

* HTML
* CSS
* Vanilla JavaScript
* Chart.js
* Socket.IO client

Main UI modules include:

* Home AI workspace
* Devices tab
* Alerts tab
* Prompts tab
* Profile tab
* Reasoning drawer
* Device history modal
* Prompt management modal
* Authentication views

The frontend supports realtime synchronization with backend telemetry and operational state changes.

---

## 7. Authentication & Session Management

The platform includes a local authentication system with protected workspace access.

Authentication features include:

* login
* access-code protected registration
* password hashing
* session persistence
* protected API routes
* username updates
* password updates
* account deletion workflows

User sessions are maintained using Flask session management.

---

## 8. Prompt Workflow System

The platform includes a reusable operational prompt system.

Prompt workflows support:

* default prompts
* custom prompts
* prompt categories
* slash-command integration
* prompt search
* prompt filtering
* persistent storage

Prompts are synchronized between the Prompts tab and the AI chat workspace.

---

## 9. Operational Alert System

The alert subsystem continuously evaluates telemetry conditions and generates operational alerts.

Alert workflows include:

* warning alerts
* critical alerts
* acknowledge actions
* resolve actions
* realtime alert synchronization
* fleet-level operational visibility

Alerts are surfaced in both the dashboard UI and AI diagnosis workflows.

---

## 10. Context-Aware Agent Behavior

The AI agent tracks operational context across conversations.

Example:

```text
User: diagnose gateway-003
Agent: diagnoses gateway-003

User: check its alarms
Agent: understands "its" refers to gateway-003
```

This allows the assistant to maintain short-term operational context during multi-step diagnosis sessions.

---

## 11. Reasoning Trace Streaming

The backend streams intermediate reasoning events during IOA v2 execution and during supported external runtime execution.

The trace stream emits `thought`, `observation`, `final`, and `error` events. Action details are shown inside the trace payload when a runtime exposes them.

The frontend renders these events inside the realtime reasoning drawer, allowing users to inspect intermediate agent behavior during operational diagnosis.
