# IOA v3 Ops Graph

`IOA v3 · Ops Graph` is the controlled operational workflow runtime. It uses
LangGraph for request validation, workflow planning, authorization, tool
execution, KPI attachment, and deterministic final answers.

The current production-oriented evidence path is MCP-first:

```text
Web UI / Telegram
  -> Flask auth, source policy, request limits
  -> IOA v3 LangGraph policy graph
  -> authorized workflow route
       -> MCP Mongo tools for OneM2M resources
       -> MCP Loki tool for logs
       -> MCP Grafana/Prometheus tools for metrics
  -> bounded evidence
  -> final answer + reasoning trace
```

The older n8n Grafana gateway remains available for IOA v2/runtime comparison,
but company runbook scenarios 5-12 are implemented through MCP.

## Runtime Boundary

The Flask app is the agent surface. It owns:

- user authentication and sessions
- chat/prompt persistence
- source selection
- OpenAI/LLM credentials
- Telegram integration
- MCP client configuration: `MCP_SERVER_URL`, `MCP_BEARER_KEY`

The MCP server owns:

- `COMPANY_MONGODB_URI`
- Mongo namespace allowlist and read guardrails
- `GRAFANA_URL`
- `GRAFANA_USERNAME`/`GRAFANA_PASSWORD` or `GRAFANA_API_KEY`
- Loki and Prometheus datasource access
- MCP bearer-key auth, rate limits, and audit logs

Do not put company MongoDB, Loki, Grafana, or Prometheus credentials in the
Flask app `.env`.

## Planner & Routing

IOA v3 uses a hybrid planner:

- A semantic planner proposes one or more workflows from the user's natural
  language request.
- A deterministic taxonomy remains as a fallback when the semantic planner
  returns invalid JSON, unsupported tools, or low-confidence plans.
- A policy verifier is always the final gate. It checks tool allowlists, source
  permissions, params, and execution budget before any workflow runs.

The graph emits streamed SSE events:

```text
thought
observation
final
error
```

These events power the UI reasoning trace and are also useful for report
generation.

## MCP Tool Families

| IOA v3 workflow family | MCP tool family | Evidence |
|---|---|---|
| OneM2M resource/flow checks | `mongo_find` and related Mongo tools | `IDENTITY`, `AE`, `CNT`, `CIN`, `SUBSCRIPTION`, `URI_MAPPER` |
| Log checks | `loki_query_range` | service/device/request filtered Loki logs |
| RabbitMQ metrics | `grafana_query`, `grafana_query_range` | queue backlog and trend |
| EMQX metrics | `grafana_query_range` | dropped-message and reconnect trends |
| Kubernetes metrics | `grafana_query` | pod CPU/memory, restarts, phase, OOM/CrashLoop, node pressure |

Grafana's `smartquery` response may use Grafana dataframe shape rather than the
classic Prometheus API `data.result` shape. IOA v3 normalizes both formats
before generating metric answers.

## Implemented Runbook Scenarios

See [OneM2M Operational Scenario Mapping](ONEM2M_OPERATIONAL_SCENARIOS.md) for
full prompt and metric details.

| Scenario | Title | Route |
|---:|---|---|
| 5 | Command Downlink Debug | MCP Mongo + MCP Loki |
| 6 | Telemetry Uplink Debug | MCP Mongo + MCP Loki |
| 7 | Device Resource Check | MCP Mongo + MCP Loki |
| 8 | RabbitMQ Top Backlog | MCP Prometheus instant query |
| 9 | RabbitMQ Linear Queue Growth | MCP Prometheus range query |
| 10 | EMQX Dropped Messages | MCP Prometheus range query |
| 11 | EMQX Reconnect Trend | MCP Prometheus range query |
| 12 | Kubernetes Resource Check | MCP Prometheus instant queries |

## Environment

Flask app:

```env
COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=http://127.0.0.1:8000/mcp
MCP_BEARER_KEY=replace_me
IOA_V3_ENABLE_KPI_RULES=false
IOA_V3_SEMANTIC_PLANNER_ENABLED=true
```

MCP server:

```env
COMPANY_MONGODB_URI=mongodb://readonly_user:[PASSWORD]@company-mongo-host:27017/?authSource=admin&directConnection=true
COMPANY_MONGO_ALLOWED_NAMESPACES=authorization.IDENTITY,subNNotif.AE,subNNotif.SUB,datamgmt.CNT,datamgmt.CIN,datamgmt.DEVICE_TELEMETRY,datamgmt.RULE,devicemgmt.NODE,orchestration.URI_MAPPER
MCP_API_KEYS_JSON={"caller-id":"sha256_hash_of_their_raw_key"}
MCP_ENABLE_GRAFANA_TOOLS=true
GRAFANA_URL=https://your-grafana-host
GRAFANA_USERNAME=readonly_user
GRAFANA_PASSWORD=replace_me
PORT=8000
```

Use `GRAFANA_API_KEY` instead of username/password when the company provides a
service token.

## Local Setup

1. Start MCP server.

   ```bash
   source .venv/bin/activate
   python mcp_server/server.py
   ```

   Or run it on an explicit port:

   ```bash
   PORT=8000 MCP_SERVER_HOST=127.0.0.1 .venv/bin/python mcp_server/server.py
   ```

2. Start Flask app.

   ```bash
   COMPANY_DATA_ACCESS_MODE=mcp \
   MCP_SERVER_URL=http://127.0.0.1:8000/mcp \
   python app.py
   ```

3. Open the web UI and choose company data source.

4. Run any default runbook prompt or alias:

   ```text
   /cmd
   /telemetry
   /resources
   /rabbitmq
   /queue-trend
   /emqx-dropped
   /reconnect
   /k8s
   ```

## Legacy n8n Runtime Path

The n8n Grafana gateway is retained for older workflow/runtime comparison. It
is not the primary route for the company MCP runbooks.

```env
N8N_V3_WEBHOOK_URL=http://localhost:5679/webhook/grafana-ops-gateway
GRAFANA_DASHBOARD_CLIENT_URL=http://127.0.0.1:5050
GRAFANA_TOOL_ACCESS_MODE=n8n
```

Use this path only when intentionally testing the older Grafana gateway shape
or legacy n8n workflow import:

```bash
python3 scripts/mock_grafana_dashboard_client.py --port 5050
N8N_PORT=5679 n8n
python3 scripts/check_ioa_v3_n8n_workflow.py --tool grafana_redis_health
```

## Troubleshooting

- `401 Unauthorized` on `/mcp`: `MCP_BEARER_KEY` does not match a hash in
  `MCP_API_KEYS_JSON`.
- `429 Too Many Requests`: MCP caller rate limit was hit. Wait for
  `retry_after`, reduce batch size, or adjust `MCP_RATE_LIMIT_REQUESTS`.
- `MCP client dependency is not installed`: run Flask with the project
  virtualenv that includes `mcp`.
- Metric answer says no samples: verify metric names, labels, scrape targets,
  and datasource through MCP `grafana_list_datasources`.
- Scenario 11 should not require a `device_id`. It starts from aggregate EMQX
  reconnect metrics and only derives device candidates from logs when evidence
  exists.
- Scenario 12 top pod CPU/memory are evidence, not automatic root cause. The
  answer should flag follow-up only when there is high restart count, abnormal
  phase, `OOMKilled`, `CrashLoopBackOff`, or node pressure.

## Verification

Run focused workflow tests:

```bash
.venv/bin/python -m unittest tests.test_ioa_v3_workflow -v
```

Generate a report from platform stream output:

```bash
.venv/bin/python scripts/collect_mcp_runbook_report.py
```

The Excel report is written to:

```text
outputs/mcp_runbook_report/mcp_operational_runbook_report.xlsx
```
