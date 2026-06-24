# OneM2M Operational Scenario Mapping

This document maps the company-provided IoT Platform operational scenarios to
the current IOA v3 architecture. The source file describes command delivery,
telemetry ingestion, resource checks, RabbitMQ, EMQX, and Kubernetes debugging
flows.

## Main Takeaway

The new scenarios are more specific than the earlier KPI pilot backlog. They
require a typed incident-triage layer that can correlate:

* adapter/core logs
* OneM2M resource records
* RabbitMQ and EMQX metrics
* Kubernetes pod/resource evidence
* user-provided identifiers such as device ID, AE ID, request ID, payload, and
  time range

The agent should not receive arbitrary shell, kubectl, Grafana, Prometheus, or
MongoDB authority. Each step should be exposed through bounded read-only tools
or approved API adapters.

## Scenario Groups

| Group | Company scenario | Current coverage | Needed next |
|---|---|---|---|
| Command downlink debug | Device does not receive command | Partial Company DB and logs coverage | Add typed OneM2M command-flow evidence tool |
| Telemetry uplink debug | Telemetry not received by backend | Partial telemetry coverage and logs coverage | Add typed OneM2M telemetry-flow evidence tool |
| Device/resource check | Check whether device X is on platform | Partial inventory/CNT/CIN coverage | Add resource existence summary across IDENTITY, AE, CNT, CIN, SUB, URI_MAPPER |
| RabbitMQ backlog | Top queues with high message count | `grafana_queue_backlog` exists | Add top queue threshold and namespace/time params |
| RabbitMQ trend | Queue grows linearly over time | Not covered | Add queue trend endpoint/tool |
| EMQX dropped messages | Message dropped increases | `grafana_emqx_health` partial | Add explicit dropped-message endpoint/tool |
| EMQX connect/disconnect | Reconnect loop or onboarding spike | `grafana_emqx_health` partial | Add explicit connected/disconnected trend endpoint/tool |
| Kubernetes resources | CPU, memory, restart, pod status, logs | `grafana_k8s_health` and `grafana_logs` partial | Add pod/service scoped params and latest error-log evidence |

## Safe Tool Plan

### Company DB Resource Tool

Add a backend read tool that accepts:

```text
device_id
ae_id
request_id
resource_name
payload_hint
time_range
application_domain
```

It should return a normalized resource table:

```text
IDENTITY
AE
CNT_COMMAND
CNT_TELEMETRY
SUBSCRIPTION
CIN
URI_MAPPER
```

The current proxy allowlist already includes:

```text
authorization.IDENTITY
datamgmt.CNT
datamgmt.CIN
```

The new scenarios require these reviewed namespaces:

```text
subNNotif.AE
subNNotif.SUB
orchestration.URI_MAPPER
```

These namespaces are now part of the default Company MongoDB read proxy
allowlist because they were confirmed in the company MongoDB schema. The next
step is to confirm the exact fields and projections for each typed evidence
tool.

### Log Evidence Tool

Expose logs through Grafana/Loki or a company-owned log adapter, not raw
`kubectl logs`. The tool should allow:

```text
service
device_id
ae_id
request_id
payload_hint
time_range
limit
```

Initial service allowlist:

```text
iot-http-api
iot-mqtt-client-adapter
core services confirmed by lead
emqx
```

### Grafana Metric Tools

Existing tools:

```text
grafana_queue_backlog
grafana_throughput
grafana_emqx_health
grafana_k8s_health
grafana_logs
```

Add or extend approved adapter endpoints for:

```text
grafana_queue_trend
grafana_emqx_dropped
grafana_emqx_connection_trend
grafana_k8s_pod_resources
```

The adapter should own PromQL details such as `topk`, `sum by(queue)`, and
`rate(...)`. IOA v3 should choose an approved workflow, not generate arbitrary
PromQL at runtime.

## Recommended Implementation Order

1. Update scenario backlog and prompts with the company-provided flows.
2. Confirm DB namespaces and field names with the lead.
3. Extend `COMPANY_MONGO_ALLOWED_NAMESPACES` only for approved collections.
4. Build one typed resource summary tool for device/AE/container/subscription
   evidence.
5. Add Grafana adapter endpoints for queue trend and EMQX dropped/connection
   trends.
6. Add IOA v3 workflow routes and tests for the new tools.
7. Run the pilot scenarios and collect pass/fail notes.

The web Prompt catalog includes default `OneM2M Ops` prompt cards for these
flows. They are placeholders until the typed DB/log/Grafana tools above are
implemented and connected to the approved company sources.

## Questions For Lead

* Which database owns `AE`: `datamgmt`, `subNNotif`, or another namespace?
* Are `subNNotif.SUB` and `orchestration.URI_MAPPER` readable by the agent
  account?
* Which log backend should the agent use: Loki/Grafana, Kubernetes API, or a
  service-owned adapter?
* What are the official service names for adapter and core pods?
* What time range format should operators provide?
* Which Grafana datasource/panel owns RabbitMQ, EMQX, and Kubernetes metrics?
* Should the agent show query commands in traces, or only normalized evidence?
