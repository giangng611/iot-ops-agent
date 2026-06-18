# IOA v3 Grafana Ops Orchestrator

IOA v3 is a separate runtime for Grafana operational workflows. The public
product label is `IOA v3 · Grafana Ops Orchestrator`; internally it keeps
LangGraph as the policy and reasoning layer while n8n executes approved
Grafana workflow steps.

## Runtime Boundary

```text
Web UI
  -> Flask auth, source policy, rate limit
  -> IOA v3 LangGraph policy graph
  -> n8n grafana_ops_gateway webhook
  -> Grafana Dashboard Client API
  -> n8n normalized response
  -> IOA v3 KPI rule attachment and final answer
```

LangGraph decides which workflow is allowed. n8n does not receive arbitrary
HTTP authority from the model. The payload sent to n8n contains one approved
tool, one approved path, and only allowlisted params.

## Environment

```bash
N8N_V3_WEBHOOK_URL=http://localhost:5679/webhook/grafana-ops-gateway
GRAFANA_DASHBOARD_CLIENT_URL=http://127.0.0.1:5050
IOA_V3_ENABLE_KPI_RULES=false
```

`N8N_WEBHOOK_URL` remains available for the older `IOA v2 · n8n` runtime.
Use a separate local n8n port for IOA v3 when the company still needs the
existing n8n evaluation workflow:

```bash
N8N_PORT=5679 n8n
```

In production, using the same managed n8n instance is fine as long as IOA v3
has a distinct webhook path, credentials, and workflow ownership boundary.

## Config Files

`config/grafana_tools.json` defines the allowlisted Grafana tools:

- tool name
- workflow id
- HTTP method
- path
- allowed params
- description

`config/grafana_kpi_rules.json` maps Grafana tools to KPI semantics from the
monitoring KPI workbook:

- KPI name
- aspect
- priority
- good/warning/critical semantics
- implementation status

KPI rules are disabled by default because the workbook may contain internal
company operating semantics. Enable them only after review:

```bash
export IOA_V3_ENABLE_KPI_RULES=true
```

## n8n Gateway Shape

Create or import one local n8n workflow named `IOA v3 - Grafana Ops Gateway`.
The importable workflow is stored in:

```text
workflows/n8n/ioa_v3_grafana_ops_gateway.json
```

The workflow shape is:

```text
Webhook /webhook/grafana-ops-gateway
  -> Validate body.workflow.tool/path/params
  -> Switch workflow.workflow_id
  -> HTTP Request to Grafana Dashboard Client
  -> Normalize evidence and return JSON from the last node
```

Start with these workflow branches because they match the current Grafana tool
registry:

- `grafana_platform_service_health`
- `grafana_queue_backlog`
- `grafana_throughput`
- `grafana_http_health`
- `grafana_java_errors`
- `grafana_trace_metrics`
- `grafana_logs`
- `grafana_emqx_health`
- `grafana_k8s_health`
- `grafana_redis_health`
- `grafana_mongodb_health`
- `grafana_mysql_health`
- `grafana_linux_health`

The workflow should build its outbound URL from:

- `body.grafana_client.base_url`
- `body.workflow.path`
- filtered query params from `body.workflow.params`

Do not allow the workflow to accept arbitrary URLs from the model or user.

The n8n response should be JSON:

```json
{
  "response": "Short final answer or workflow summary",
  "evidence": {
    "level": "good",
    "example_metric": 123
  },
  "steps": [
    {
      "thought": "Called approved Grafana endpoint.",
      "action": "GET /grafana/redis",
      "output": {
        "level": "good"
      }
    }
  ]
}
```

## Security Notes

- Do not put Grafana tokens or DB credentials in the workbook or repo.
- n8n should call only the path supplied by the backend payload.
- The backend filters params before sending the request to n8n.
- IOA v3 traces show the selected workflow, HTTP path, bounded evidence, and
  KPI rules applied.
- The Alerts tab still supports local fallback rules until the official
  Grafana/company alert feed is mapped.

## Local Setup From Scratch

1. Start the Grafana Dashboard Client API.

   The Postman collection supplied for this project points at port `5050`.
   IOA v3 expects the same default:

   ```bash
   export GRAFANA_DASHBOARD_CLIENT_URL=http://127.0.0.1:5050
   ```

   This value is not the Grafana dashboard UI URL. It must be an API adapter
   that exposes the allowlisted endpoints used by `config/grafana_tools.json`,
   for example `/grafana/redis` and `/platform/service-health`. A normal
   Grafana dashboard link usually points to pages like `/d/...` and cannot be
   used directly by this n8n workflow without a separate Grafana API adapter
   and credentials.

   Verify the client is reachable:

   ```bash
   curl -s http://127.0.0.1:5050/health
   ```

   If the real Grafana Dashboard Client is not available yet, run the local mock
   client to validate the n8n flow:

   ```bash
   python3 scripts/mock_grafana_dashboard_client.py --port 5050
   ```

2. Start a separate n8n instance for IOA v3.

   Use port `5679` so the older `IOA v2 · n8n` evaluation workflow can keep
   using port `5678`.

   ```bash
   N8N_PORT=5679 n8n
   ```

   Then open:

   ```text
   http://localhost:5679
   ```

3. Import the workflow.

   In n8n:

   ```text
   Workflows -> Import from File -> workflows/n8n/ioa_v3_grafana_ops_gateway.json
   ```

   Save the workflow and activate it. The production webhook URL should be:

   ```text
   http://localhost:5679/webhook/grafana-ops-gateway
   ```

   If the workflow is not active, n8n may only expose a test webhook URL. IOA v3
   should use the production `/webhook/...` URL after activation.

   In the Webhook node, use:

   ```text
   Respond: When Last Node Finishes
   ```

   The last node must be `Normalize IOA v3 Response`, and it must return the
   final JSON body containing `response`, `evidence`, and `steps`.

4. Configure the Flask app environment.

   ```bash
   export N8N_V3_WEBHOOK_URL=http://localhost:5679/webhook/grafana-ops-gateway
   export GRAFANA_DASHBOARD_CLIENT_URL=http://127.0.0.1:5050
   export IOA_V3_ENABLE_KPI_RULES=false
   ```

   Keep the older `N8N_WEBHOOK_URL` separate. IOA v3 intentionally does not
   fall back to that legacy variable.

5. Probe the n8n gateway directly.

   ```bash
   python3 scripts/check_ioa_v3_n8n_workflow.py \
     --webhook-url http://localhost:5679/webhook/grafana-ops-gateway \
     --tool grafana_redis_health
   ```

   To test against a non-local Grafana Dashboard Client API:

   ```bash
   python3 scripts/check_ioa_v3_n8n_workflow.py \
     --webhook-url http://localhost:5679/webhook/grafana-ops-gateway \
     --tool grafana_redis_health \
     --grafana-base-url https://your-grafana-client-api.example.com
   ```

   Expected result: HTTP `200` and a JSON body containing `response`,
   `evidence`, and `steps`.

6. Start IoT Ops Agent.

   ```bash
   APP_DB_BACKEND=supabase \
   APP_DB_FALLBACK_ENABLED=false \
   N8N_V3_WEBHOOK_URL=http://localhost:5679/webhook/grafana-ops-gateway \
   GRAFANA_DASHBOARD_CLIENT_URL=http://127.0.0.1:5050 \
   python3 app.py
   ```

7. Test from the UI.

   The default chat runtime is now `IOA v3 · Grafana Ops Orchestrator`.
   Try prompts such as:

   - `check redis health`
   - `show platform service health`
   - `show rabbitmq queue backlog`
   - `show recent error logs for emqx`

   The reasoning trace should show LangGraph policy gates, the approved n8n
   workflow call, and KPI rule attachment before final answer generation.

## Troubleshooting

- `N8N_V3_WEBHOOK_URL is not configured`: set the v3-specific env var. Do not
  use `N8N_WEBHOOK_URL` for IOA v3.
- n8n returns `404`: the workflow is probably not active, or the URL is using
  `/webhook-test/...` instead of `/webhook/...`.
- n8n returns an error about an unapproved path: the backend and workflow
  allowlists are out of sync. Compare `config/grafana_tools.json` with the
  `allowedPaths` list inside the imported workflow.
- n8n returns connection refused for `127.0.0.1:5050`: start the Grafana
  Dashboard Client API first, run the local mock client with
  `python3 scripts/mock_grafana_dashboard_client.py --port 5050`, or set
  `GRAFANA_DASHBOARD_CLIENT_URL` to the correct address reachable from n8n.
- `scripts/check_ioa_v3_n8n_workflow.py` reports `empty_response_body=true`:
  the webhook is registered, but n8n is responding immediately before the final
  node returns JSON. Open the Webhook node and set `Respond` to
  `When Last Node Finishes`, save, deactivate, and reactivate the workflow.
- IOA v3 answers that official alerts are pending: that is expected until the
  official Grafana/company alert feed is mapped into the Alerts tab.
