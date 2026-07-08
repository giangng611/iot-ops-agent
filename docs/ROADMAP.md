# Roadmap

Future improvements and long-term direction for IoT Ops Agent.

This roadmap is readiness-based. Earlier calendar milestones are kept only as
planning context because the project depends on company database handoff,
Grafana access, and operational rule review. Current work should prioritize
evidence quality and pilot readiness over date-driven feature expansion.

---

## Current Readiness

### Demo-ready Foundation

* Web workspace with authenticated chat, prompt workflows, profile controls,
  telemetry views, alert handling, and reasoning traces
* Simulator/fallback telemetry path for local verification and degraded-source
  testing
* Company DB source selection, visible fallback behavior, and bounded read-only
  MongoDB access through MCP
* Telegram PoC with account linking, allowlists, commands, and shared IOA v3
  policy/runtime behavior
* IOA v3 Ops Graph with LangGraph policy gates, hybrid semantic/deterministic
  workflow planning, MCP tool execution, and evidence traces
* Grafana/Prometheus metric mapping and initial KPI rule mapping files
* Security tests and proof docs for app data, MongoDB guardrails, Supabase RLS,
  and Telegram webhook authentication

### Waiting On Company Inputs

* Final production Company DB schema/collections and allowed read scope
* Official alert/KPI rule ownership and good/warning/critical semantics
* Senior review of the MCP-backed runbook outputs and expected answers
* Official KPI/rule ownership and good/warning/critical semantics

### Near-term Focus

1. Review and freeze MCP-backed scenarios 5-12 with the lead.
2. Add deeper log correlation where metric-only scenarios need service-specific
   follow-up.
3. Map official KPI rules once monitoring ownership confirms thresholds.
4. Rerun benchmark and acceptance tests against frozen company-task snapshots.

The current seed scenario backlog lives in
`eval/company_pilot_scenarios.json`; use
`docs/PILOT_SCENARIO_CHECKLIST.md` to convert company-provided scenarios into
repeatable acceptance tests.

The company OneM2M debug scenarios are mapped in
`docs/ONEM2M_OPERATIONAL_SCENARIOS.md`. They require typed read-only DB, log,
and Grafana adapter tools before they should be treated as production-ready.

---

## Infrastructure & Deployment

### Planned Improvements

* Row Level Security policy design if browser-side Supabase clients are added
* Docker containerization
* production-ready deployment architecture
* custom domain support
* scalable telemetry workers
* improved environment configuration

### Completed / In Progress

* MongoDB telemetry storage path
* Supabase/Postgres app-data migration path
* SQLite legacy/fallback storage for degraded local cases
* storage status and migration integrity checks
* MCP-backed Company DB, Loki, Grafana, and Prometheus path

### Deployment Evolution

```text
Flask Application
        ↓
Gunicorn / Gevent
        ↓
Supabase/Postgres app data
        ↓
MongoDB telemetry
        ↓
Cloud Infrastructure
        ↓
Custom Domain + HTTPS
```

---

## Realtime Systems

Planned realtime infrastructure improvements include:

* MQTT telemetry ingestion
* event-driven telemetry pipelines
* device grouping
* device metadata management
* realtime notification toasts
* distributed telemetry streams
* alert synchronization improvements
* background telemetry workers

---

## AI & Agent Systems

Future AI improvements may include:

* multi-agent orchestration
* anomaly detection
* predictive maintenance analysis
* root-cause investigation chains
* operational memory systems
* runbook retrieval
* automated remediation recommendations
* contextual incident summarization

### Runtime Evaluation Status

Completed local runtime evaluations:

* IOA v2 · Custom Python
* IOA v2 · LangChain
* IOA v2 · LangGraph
* IOA v2 · n8n
* IOA v2 · Dify

Current operational runtime:

* IOA v3 · Ops Graph, using LangGraph policy/routing and MCP-backed MongoDB,
  Loki, and Grafana/Prometheus evidence

The benchmark runner and blind AI-as-judge pipeline are implemented. The next
evaluation milestone is to rerun candidates against frozen company-task
snapshots and report critical errors separately from averages. Historical
manual scores are not considered current runtime-selection evidence.

Potential future runtime candidates:

* Flowise
* CrewAI
* local model runtime integration

Potential future agent capabilities:

```text
Telemetry anomaly detected
        ↓
AI investigation chain
        ↓
Root-cause analysis
        ↓
Operational recommendations
        ↓
Suggested remediation workflow
```

---

## Product Features

Future platform-level improvements:

* organization/workspace support
* role-based access control (RBAC)
* admin dashboard
* notification preferences
* email or Slack alert delivery
* exportable operational reports
* saved investigation templates
* shared operational prompt libraries

---

## Observability & Analytics

Planned observability improvements include:

* MCP-backed Grafana/Prometheus evidence integration
* official KPI/rule calibration from company monitoring ownership
* historical fleet-wide analytics
* device comparison dashboards
* incident timelines
* alert history visualization
* operational trend analysis
* device dependency graphs
* geographic device maps
* long-term telemetry retention

---

## Security & Authentication

Future authentication improvements may include:

* production-grade authentication
* OAuth integration
* password reset workflows
* audit logging
* API rate limiting
* account recovery systems
* multi-user access controls
* shared/distributed API and Company DB rate limiting

---

## Frontend & UX

Potential UI and UX improvements:

* theme customization
* responsive mobile layout
* keyboard shortcuts
* advanced dashboard customization
* configurable alert panels
* improved loading states
* toast notifications
* accessibility improvements

---

## Long-Term Vision

IoT Ops Agent is designed as a simulated AI-assisted operations platform that can evolve toward real-world operational observability systems.

The long-term goal is to transform the current PoC into one source-aware,
auditable company operational agent that synchronizes approved systems behind
typed tools and policy controls.

Potential production use cases include:

* monitoring IoT device fleets
* diagnosing connectivity failures
* analyzing telemetry trends
* prioritizing operational incidents
* assisting operators during investigations
* supporting AI-assisted operational workflows
* reducing manual troubleshooting effort
