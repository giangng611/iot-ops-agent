# IoT Ops AI Agent

## Description

IoT Ops AI Agent is a Python-based AI operations assistant powered by the OpenAI API.

The project simulates a simple AI agent workflow capable of:
- selecting tools,
- retrieving operational data,
- and generating structured responses for IoT monitoring scenarios.

---

## Features

- OpenAI API integration
- LLM-based tool selection
- Simulated IoT monitoring tools
- Structured operational responses
- Conversation memory
- JSON-based tool outputs
- Basic AI agent workflow architecture
- Error handling and API management

---

## Example Workflow

```text
User Request
    ↓
LLM Tool Selection
    ↓
Tool Execution
    ↓
Structured JSON Output
    ↓
LLM Analysis
    ↓
Final Operational Response
```

Example request:

```text
Check device status
```

Example response:

```text
1. Summary
2. Evidence
3. Suggested next action
```

---

## Tech Stack

- Python
- OpenAI API
- GPT-4.1-mini
- dotenv

---

## Installation

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