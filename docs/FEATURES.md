# Features

This document describes the main product features in IoT Ops Agent.

---

## Agent Modes

## IOA v1 — Single-Step Tool Calling

- Selects one tool per request
- Produces direct answers
- Useful for simple device checks
- Demonstrates basic LLM tool use

---

## IOA v2 — Multi-Step Reasoning Agent

- Uses ReAct-style investigation
- Calls multiple tools when needed
- Streams reasoning trace live
- Supports system-level and device-level diagnosis
- Tracks previous device context

---

## Realtime Telemetry

The telemetry simulator generates changing device metrics over time.

Each device has:

- CPU usage
- memory usage
- heartbeat delay
- status
- log message
- alarm state

---

## WebSocket Live Updates

The frontend updates automatically using WebSocket events.

Live updates affect:

- device table
- alert badge
- alert center
- fleet charts

---

## Devices Tab

The Devices tab includes:

- realtime device inventory
- status filtering
- search by device ID
- sorting by priority, CPU, memory, heartbeat, and timestamp
- priority scoring
- diagnose button
- history button

---

## Fleet Charts

Fleet-level charts include:

- health distribution
- average CPU usage
- average memory usage
- average heartbeat delay

---

## Device History Charts

Each device has a historical telemetry chart showing:

- CPU trend
- memory trend
- heartbeat delay trend
- warning threshold baselines

---

## Alerts Dashboard

The Alerts tab shows:

- active warning devices
- active critical devices
- alert counts
- device-level alert details
- diagnose and history actions

---

## Chat Workspace

The chat workspace supports:

- IOA v1 and IOA v2 mode selection
- streaming AI responses
- live reasoning trace drawer
- persistent chat history
- searchable chat history
- pinned chats
- delete chat action

---

## Authentication

The app includes local authentication:

- register account
- login
- logout confirmation
- Flask session handling
- password hashing
- password update workflow

---

## Profile Workspace

The Profile tab includes:

- account overview
- security settings
- chat history explanation
- workspace details
- notification explanation
- interactive right-side profile drawer