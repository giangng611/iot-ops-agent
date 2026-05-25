# IoT Ops AI Agent

## Description

IoT Ops AI Agent is a Python-based AI operations assistant powered by the OpenAI API.

The project demonstrates the evolution from:
- a single-step LLM tool-calling assistant,
to
- a multi-step reasoning AI agent capable of iterative investigation workflows.

The system simulates IoT operational diagnostics using:
- tool orchestration,
- structured observations,
- conversation memory,
- and reasoning loops.

---

# Features

## Week 1 — Single-Step Tool Calling

- OpenAI API integration
- LLM-based tool selection
- Structured operational responses
- Conversation memory
- JSON-based tool outputs

Workflow:

```text
User Request
    ↓
Tool Selection
    ↓
Tool Execution
    ↓
LLM Response
```

---

## Week 2 — Multi-Step Reasoning Agent

- Iterative reasoning loop
- Multi-tool orchestration
- Observation-driven analysis
- Step-by-step investigation
- AI agent workflow architecture

Workflow:

```text
User Request
    ↓
Thought
    ↓
Action (Tool)
    ↓
Observation
    ↓
Reason Again
    ↓
More Tools if Needed
    ↓
Final Diagnosis
```

---

# Available Tools

- `check_device_status`
- `get_recent_logs`
- `check_alarm_rules`

---

# Example Week 2 Execution

```text
User: diagnose the system issue

--- Iteration 1 ---
Thought → check device health
Action → check_device_status

--- Iteration 2 ---
Thought → inspect logs
Action → get_recent_logs

--- Iteration 3 ---
Thought → verify alarms
Action → check_alarm_rules

Final Diagnosis Generated
```

---

# Tech Stack

- Python
- OpenAI API
- GPT-4.1-mini
- dotenv

---

# Project Structure

```text
iot-ops-agent/
├── main.py
├── tools.py
├── prompts.py
├── agents/
│   ├── __init__.py
│   ├── week1_agent.py
│   └── week2_agent.py
├── requirements.txt
├── README.md
├── .env
└── .gitignore
```

---

# Installation

Clone the repository:

```bash
git clone <your-repo-url>
cd iot-ops-agent
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file:

```text
OPENAI_API_KEY=your_api_key_here
```

Run the project:

```bash
python3 main.py
```

---

# Agent Modes

When the application starts, choose an agent mode:

```text
1. Week 1 - Single-step tool calling
2. Week 2 - Multi-step reasoning agent
```

Use:

```text
/home
```

to return to the mode selection menu.

Use:

```text
exit
```

to quit the application.

---

# Learning Focus

This project focuses on:
- AI agent fundamentals
- LLM orchestration
- Tool calling
- ReAct-style reasoning loops
- Operational AI workflows
- Observability-oriented systems
- Prompt engineering
- Backend AI architecture

---

# Future Improvements

- Autonomous planning
- Real API integrations
- Telegram bot support
- LangChain / LangGraph integration
- MongoDB integration
- Grafana integration
- Advanced memory systems
- Real observability workflows