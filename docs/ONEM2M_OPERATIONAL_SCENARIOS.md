# OneM2M Operational Scenario Mapping

This document maps the company IoT Platform operational runbooks to the current
IOA v3 + MCP architecture.

## Current Status

Runbook scenarios 5-12 are integrated in `IOA v3 · Ops Graph` and execute
through the MCP server for company operational evidence.

```text
Operator prompt
  -> Flask /api/diagnose-stream
  -> IOA v3 LangGraph policy graph
  -> MCP server
       -> MongoDB resources and OneM2M evidence
       -> Loki logs
       -> Grafana/Prometheus metrics
  -> deterministic final answer + reasoning trace
```

The Flask app is the agent/runtime surface. It must not hold direct company
MongoDB, Loki, Grafana, or Prometheus credentials. Those credentials live only
in the company-provided MCP service environment. The public `mcp_server/`
folder contains only the integration contract.

## Scenario Coverage

| Scenario | Prompt title | Required operator input | Evidence route | Status |
|---:|---|---|---|---|
| 5 | Command Downlink Debug | `device_id` | MCP Mongo + MCP Loki | Implemented |
| 6 | Telemetry Uplink Debug | `device_id` | MCP Mongo + MCP Loki | Implemented |
| 7 | Device Resource Check | `device_id` | MCP Mongo + MCP Loki | Implemented |
| 8 | RabbitMQ Top Backlog | none; defaults namespace `test` | MCP Prometheus instant query | Implemented |
| 9 | RabbitMQ Linear Queue Growth | optional time range/queue | MCP Prometheus range query | Implemented |
| 10 | EMQX Dropped Messages | optional time range | MCP Prometheus range query | Implemented |
| 11 | EMQX Reconnect Trend | none; aggregate-first | MCP Prometheus range queries | Implemented |
| 12 | Kubernetes Resource Check | optional namespace/service/pod | MCP Prometheus instant queries | Implemented |

## Scenario Details

### 5. Command Downlink Debug

Checks why a device did not receive a command.

Evidence:

- `IDENTITY`
- `AE`
- `cnt_command`
- `SUBSCRIPTION`
- `URI_MAPPER`
- latest command `CIN`
- device-filtered Loki logs when available

The final answer reports resource presence exactly from DB/log evidence and
uses "Likely Failure Point" rather than claiming a root cause without log
correlation.

### 6. Telemetry Uplink Debug

Checks why telemetry from a device did not reach the backend.

Evidence:

- `IDENTITY`
- `AE`
- `cnt_telemetry`
- latest telemetry `CIN`
- backend `SUBSCRIPTION`
- notify/backend delivery evidence from logs when available

When telemetry `CIN` is present, the next action is to correlate latest
telemetry `CIN` with backend subscription notify logs, adapter receive logs,
and backend delivery evidence.

### 7. Device Resource Check

Checks whether a device is registered and whether required OneM2M resources
exist.

Evidence table:

- `IDENTITY`
- `AE`
- `CNT`
- `CIN`
- `SUBSCRIPTION`
- `URI_MAPPER`

The answer must list exactly which resources are present or missing and must
not infer presence from naming similarity alone.

### 8. RabbitMQ Top Backlog

PromQL:

```promql
topk(10, sum by (queue) (rabbitmq_queue_messages{namespace="test",job="monitoring/rabbitmq"}))
```

The answer reports the highest queue, message count, threshold assessment, and
consumer/service follow-up.

### 9. RabbitMQ Linear Queue Growth

PromQL:

```promql
sum by (queue) (rabbitmq_queue_messages{namespace="test",job="monitoring/rabbitmq"})
```

The agent uses range samples to compute queue start, end, delta, and whether
the series is monotonically increasing enough to indicate linear growth.

### 10. EMQX Dropped Messages

PromQL:

```promql
sum(emqx_messages_dropped{namespace="emqx",job="emqx"})
```

The answer reports dropped delta and latest dropped value. A flat counter is
not treated as active dropping.

### 11. EMQX Reconnect Trend

Scenario 11 is aggregate-first and does not require `device_id`.

PromQL:

```promql
sum(rate(emqx_client_connected{namespace="emqx",job="emqx"}[1m]))
sum(rate(emqx_client_disconnected{namespace="emqx",job="emqx"}[1m]))
```

If aggregate reconnect evidence suggests a spike, the next step is to identify
device candidates from MQTT adapter or EMQX logs before checking device
resources.

### 12. Kubernetes Resource Check

Checks `DEFAULT_K8S_NAMESPACE` by default. The public template uses
`iot-platform`; set the variable to your Kubernetes namespace.

Evidence:

- top pod CPU
- top pod memory
- restart counts
- pod phase
- waiting reasons such as `CrashLoopBackOff`, `ImagePullBackOff`, `ErrImagePull`
- last terminated reasons such as `OOMKilled` or `Error`
- node CPU
- node memory

Pod CPU/memory is reported as top-consumer evidence. The answer only flags
follow-up when there is a concrete abnormal signal such as high restart count,
abnormal phase, `OOMKilled`, `CrashLoopBackOff`, or high node pressure.

## Prompt Catalog

Default runbook prompts appear first for company/MongoDB mode. They are shown
by title, not as "scenario N", in the platform UI. Current shortcuts:

| Shortcut | Prompt |
|---|---|
| `/cmd` | Command Downlink Debug |
| `/telemetry` | Telemetry Uplink Debug |
| `/resources` | Device Resource Check |
| `/rabbitmq` | RabbitMQ Top Backlog |
| `/queue-trend` | RabbitMQ Linear Queue Growth |
| `/emqx-dropped` | EMQX Dropped Messages |
| `/reconnect` | EMQX Reconnect Trend |
| `/k8s` | Kubernetes Resource Check |

Simulator mode uses a separate, simpler fallback prompt set. Custom prompts do
not receive shortcut aliases.

## Verification

The workflow tests cover:

- routing scenarios 5-12 to the expected tool
- scenario 11 not treating `candidates` as a device id
- MCP Prometheus execution for metric scenarios
- Grafana dataframe parsing
- deterministic answer formatting
- prompt catalog ordering and aliases

Run:

```bash
.venv/bin/python -m unittest tests.test_ioa_v3_workflow -v
```

The report workbook generated during integration lives under:

```text
outputs/mcp_runbook_report/mcp_operational_runbook_report.xlsx
```

This report contains final answers and reasoning traces collected through the
Flask `/api/diagnose-stream` platform route.
