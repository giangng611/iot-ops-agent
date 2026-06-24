# Pilot Scenario Checklist

Use this checklist when the company provides detailed operational scenarios.
The goal is to turn each scenario into repeatable evidence, not to add new
agent behavior before the required source/tool mapping is clear.

## Scenario Template

```text
Scenario ID:
Business situation:
User prompt:
Expected source:
Expected tools:
Required evidence:
Expected answer focus:
Pass criteria:
Actual result:
Gaps / follow-up:
Owner sign-off:
```

## Seed Scenario Set

The initial scenario file is:

```text
eval/company_pilot_scenarios.json
```

It covers:

* disconnected company devices
* telemetry coverage and unmapped records
* company rule readiness and Grafana gaps
* OneM2M command downlink debugging
* OneM2M telemetry uplink debugging
* OneM2M device/resource existence checks
* API success, 5xx, and p95 latency
* RabbitMQ backlog and throughput pressure
* RabbitMQ queue trend checks
* EMQX dropped-message checks
* EMQX connect/disconnect trend checks
* infrastructure drilldown across Kubernetes, Linux, Redis, MongoDB, and MySQL
* mixed Company DB plus Grafana investigations
* manual threshold scans over company telemetry payloads
* recent warning/error logs
* Company DB unavailable with simulator fallback

See [OneM2M Operational Scenario Mapping](ONEM2M_OPERATIONAL_SCENARIOS.md) for
the company-provided command, telemetry, device-resource, queue, EMQX, and
Kubernetes scenario mapping.

## Acceptance Rules

Each accepted scenario should prove:

* the active data source is visible
* simulator fallback is never presented as company data
* every tool call is allowlisted and visible in the reasoning trace
* answers cite bounded evidence instead of inventing devices, metrics, or rules
* provisional rules are labeled as provisional
* Grafana evidence comes from an approved API/adapter or mock client, not a
  dashboard UI URL
* infrastructure evidence is not claimed as root cause unless company/device
  evidence supports the link
* result truncation is stated when only samples are shown

## Local Smoke Commands

Check the mock Grafana/n8n path:

```bash
python3 scripts/check_ioa_v3_n8n_workflow.py \
  --webhook-url http://localhost:5679/webhook/grafana-ops-gateway \
  --tool grafana_redis_health
```

Run the pilot prompt set through supported benchmark modes:

```bash
python3 -m scripts.evaluate_local_runtimes \
  --prompts eval/company_pilot_scenarios.json \
  --out eval/company_pilot_runtime_results.csv \
  --modes ioa_v3_ops
```

If external runtimes or comparison candidates are available, pass explicit
modes:

```bash
python3 -m scripts.evaluate_local_runtimes \
  --prompts eval/company_pilot_scenarios.json \
  --out eval/company_pilot_runtime_results.csv \
  --modes ioa_v3_ops,ioa_v2_custom,langchain,langgraph,n8n_webhook,dify_api
```

For Company DB or mixed scenarios, `ioa_v3_ops` asks the source resolver for
Company DB context. If Company DB is not configured yet, the result should make
the simulator fallback or policy denial visible instead of pretending company
evidence exists.

## Company Handoff Questions

Ask these before treating a scenario as production-ready:

* Which operational team owns this scenario?
* Which source is authoritative for the answer?
* Which fields identify device, timestamp, status, alarm, and measured value?
* Which collections own `AE`, `SUB`, and `URI_MAPPER` in the real Company DB?
* Which adapter/core service names should be allowlisted for log search?
* Which KPI/rule thresholds are official?
* Which Grafana panels map to API/adapter endpoints?
* What answer would count as a critical factual error?
* What evidence can be shown in a demo or public portfolio version?
