# n8n UI Runtime Integration

IoT Ops Agent supports an optional `IOA v2 · n8n` mode in the Home chat runtime selector.

## Environment

Set this in `.env`:

```env
N8N_WEBHOOK_URL=http://localhost:5678/webhook/iot-ops-eval
```

Restart Flask after changing `.env`.

## Expected n8n Webhook Contract

The Flask backend sends:

```json
{
  "message": "/overview system health",
  "prompt": "/overview system health",
  "source": "iot-ops-agent-ui"
}
```

n8n should return one of these simple response shapes:

```json
{
  "response": "final answer text",
  "steps": []
}
```

or:

```json
{
  "answer": "final answer text"
}
```

or plain text.

## UI Test Flow

1. Start n8n locally.
2. Create a workflow with a Webhook trigger at `/webhook/iot-ops-eval`.
3. Add the AI/OpenAI workflow nodes you want to evaluate.
4. Return JSON with a `response` field.
5. Start Flask and select `IOA v2 · n8n` in the UI.
6. Run the same prompts used for LangChain/LangGraph.

The backend logs each n8n run into `benchmark_results.csv` using the mode name `IOA v2 · n8n`.

