# Dify UI Runtime Integration

IoT Ops Agent supports an optional `IOA v2 · Dify` mode in the Home chat runtime selector.

Dify is used as a self-hosted Chatflow runtime. The Flask backend packages IoT operational context, sends it to Dify through the Chat Messages API, normalizes the returned answer and steps, streams reasoning events to the UI, and logs benchmark rows into `benchmark_results.csv`.

---

## Environment

Set these values in `.env`:

```env
DIFY_API_URL=http://localhost/v1/chat-messages
DIFY_API_KEY=app-your_dify_app_api_key
DIFY_USER=iot-ops-agent-ui
```

Restart Flask after changing `.env`.

For local self-hosted Dify through Docker Compose, `DIFY_API_URL` is usually:

```text
http://localhost/v1/chat-messages
```

---

## Local Dify Setup

Recommended shallow clone:

```bash
cd ~/Desktop
git clone --depth 1 https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker-compose up -d
```

If Docker Desktop is unavailable, Colima can be used:

```bash
brew install colima docker docker-compose
colima start --cpu 4 --memory 8 --disk 60
cd ~/Desktop/dify/docker
docker-compose up -d
```

Open:

```text
http://127.0.0.1/install
```

---

## Dify App Setup

In Dify:

1. Create an admin account.
2. Choose `Create from Blank`.
3. Select `Chatflow`.
4. Name the app `IoT Ops Agent Eval`.
5. Keep the simple flow shape: `Start -> LLM -> Answer`.
6. Configure a model provider such as OpenAI.
7. Publish the app.
8. Open `API Access`.
9. Create an app API key and place it in `DIFY_API_KEY`.

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

---

## Backend Contract

The Flask backend sends a Dify Chat Messages API request with:

```json
{
  "inputs": {
    "system_prompt": "You are an IoT operations assistant...",
    "diagnosis_output_format": "Always format the final answer exactly as...",
    "operational_context": "{... JSON string ...}"
  },
  "query": "Full composed operational prompt...",
  "response_mode": "blocking",
  "user": "iot-ops-agent-ui"
}
```

For the simulator source, the operational context includes:

```json
{
  "latest_devices": [],
  "system_overview": {},
  "system_alarms": {},
  "target_device": null,
  "target_device_status": null,
  "target_device_history": []
}
```

When Company DB is active, the same field contains bounded company
operational context. If Company MongoDB is unavailable, Flask packages
simulator fallback context and identifies the active source.

Dify can return either normal text or JSON text. If the answer contains:

```json
{
  "response": "final answer text",
  "steps": []
}
```

Flask extracts `response` as the final answer and streams each item in `steps` as a reasoning trace step.

---

## UI Test Flow

1. Start Dify locally.
2. Start Flask.
3. Open IoT Ops Agent.
4. Select `IOA v2 · Dify`.
5. Run `/overview system health`.
6. Open `Show reasoning trace`.

Expected behavior:

* structured final answer
* UI-visible reasoning trace
* benchmark row appended with mode `IOA v2 · Dify`

---

## Evaluation Status

Dify is available in the shared runner through `dify_api` mode. Historical
manual scores are not current runtime-selection evidence. Use the frozen prompt
and blind judge flow in [Benchmarking](BENCHMARKING.md).

Dify reasoning steps are app-level or model-generated unless the Chatflow
explicitly invokes and returns real tool events. Trace length alone is not
evidence of database tool use.

---

## Notes

Dify self-hosting does not add Dify license cost for local testing, but model usage may incur provider API cost depending on the model configured inside Dify.
