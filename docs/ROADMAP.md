# Roadmap

Future improvements and long-term direction for IoT Ops Agent.

---

## Infrastructure & Deployment

### Planned Improvements

* PostgreSQL migration
* Supabase integration
* Docker containerization
* production-ready deployment architecture
* custom domain support
* persistent cloud storage
* scalable telemetry workers
* improved environment configuration

### Deployment Evolution

```text id="1c8qlu"
Flask Application
        ↓
Gunicorn / Gevent
        ↓
PostgreSQL
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

### Phase 1 Orchestration Evaluation

Completed local runtime evaluations:

* IOA v2 · Custom Python
* IOA v2 · LangChain
* IOA v2 · LangGraph
* IOA v2 · n8n

The current Phase 1 benchmark compares these runtimes across five shared operational prompts, including fleet overview, unhealthy-device detection, root-cause diagnosis, gateway heartbeat investigation, and active sensor alert correlation.

Next framework candidates:

* Dify
* Flowise
* CrewAI
* local model runtime integration

Potential future agent capabilities:

```text id="9e2y8z"
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
* session management improvements

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

The long-term goal is to transform the platform from a telemetry simulation environment into an AI operational copilot capable of supporting real infrastructure workflows.

Potential production use cases include:

* monitoring IoT device fleets
* diagnosing connectivity failures
* analyzing telemetry trends
* prioritizing operational incidents
* assisting operators during investigations
* supporting AI-assisted operational workflows
* reducing manual troubleshooting effort
