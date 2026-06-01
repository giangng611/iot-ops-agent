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
  "source": "iot-ops-agent-ui",
  "runtime": "n8n",
  "system_prompt": "You are an IoT operations assistant...",
  "n8n_llm_prompt": "Full prompt already composed for an n8n LLM node...",
  "diagnosis_output_format": "Always format the final answer exactly as...",
  "operational_context": {
    "latest_devices": [],
    "system_overview": {},
    "system_alarms": {},
    "target_device": null,
    "target_device_status": null,
    "target_device_history": []
  },
  "response_contract": {
    "response": "Final answer formatted exactly with DIAGNOSIS_OUTPUT_FORMAT.",
    "steps": []
  }
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
3. Add a Basic LLM Chain connected to an OpenAI Chat Model.
4. Add a Code node to normalize the LLM output into `{ response, steps }`.
5. Return the Code node item through `Respond to Webhook`.
6. Start Flask and select `IOA v2 · n8n` in the UI.
7. Run the same prompts used for LangChain/LangGraph.

The backend logs each n8n run into `benchmark_results.csv` using the mode name `IOA v2 · n8n`.

## Suggested Real LLM Workflow

Use this production workflow shape:

```text
Webhook
-> Basic LLM Chain
-> Code in JavaScript
-> Respond to Webhook
```

Prompt template for the LLM node:

Simplest option:

```text
{{$json.body.n8n_llm_prompt}}
```

Expanded option:

```text
{{$json.body.system_prompt}}

User request:
{{$json.body.message}}

Required final answer format:
{{$json.body.diagnosis_output_format}}

Operational context JSON:
{{JSON.stringify($json.body.operational_context, null, 2)}}

Return a valid JSON object only:
{
  "response": "final answer using the required format",
  "steps": [
    {
      "thought": "what information you inspected",
      "action": "which n8n node or context field you used",
      "output": "short evidence from the operational context"
    }
  ]
}
```

If the LLM node returns text instead of JSON, use a `Code in JavaScript` node to normalize the model output:

```js
const raw =
  $json.output ||
  $json.text ||
  $json.content ||
  $json.message?.content ||
  $json.response ||
  JSON.stringify($json);

let parsed;

try {
  parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
} catch (error) {
  parsed = {
    response: String(raw),
    steps: [
      {
        thought: "Generated diagnosis from IoT operational context.",
        action: "n8n_openai_node",
        output: "Model returned non-JSON text, wrapped by Code node."
      }
    ]
  };
}

return [
  {
    json: {
      response: parsed.response || parsed.answer || String(raw),
      steps: parsed.steps || [
        {
          thought: "Generated diagnosis from IoT operational context.",
          action: "n8n_openai_node",
          output: "Model produced final diagnosis."
        }
      ]
    }
  }
];
```

The `Respond to Webhook` node should return the first incoming item from the Code node, or return JSON with the same shape:

```json
{
  "response": "final diagnosis text",
  "steps": []
}
```

The Webhook node must use:

```text
Respond: Using 'Respond to Webhook' Node
```

If it is left as `Immediately`, Flask may receive an empty response body before the LLM workflow finishes.

## Local Evaluation Result

n8n was tested locally through the UI with the same five prompts used by the other runtimes:

* `/overview system health`
* `/check all unhealthy devices`
* `/diagnose system issue`
* gateway heartbeat-delay investigation
* active sensor alert correlation

Average n8n scores:

| Metric | Score |
| ------ | ----: |
| Accuracy | 4.2 |
| Tool Usage | 4.0 |
| Reasoning Clarity | 4.2 |
| Observability | 4.0 |
| Development Complexity | 4.0 |
| Integration Speed | 5.0 |
| Ecosystem | 4.0 |
| Maintainability | 4.0 |
| Avg Latency | 8.53s |

n8n showed strong integration speed and workflow-level observability, while Custom Python and LangGraph still provide deeper low-level reasoning-loop control. After the later Dify integration, n8n remains the stronger visual workflow automation option, while Dify is better suited for chatbot-native operational diagnosis because it requires less manual workflow configuration for text responses.
