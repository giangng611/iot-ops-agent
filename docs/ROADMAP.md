# Roadmap

Future improvements for IoT Ops Agent.

---

## Infrastructure

- PostgreSQL migration
- Supabase integration
- Docker deployment
- Cloud deployment
- Custom domain
- Production environment configuration

---

## Realtime Systems

- Replace polling loops with event-driven telemetry ingestion
- Add MQTT ingestion
- Add device groups
- Add device metadata management
- Add realtime notification toasts

---

## AI Improvements

- Multi-agent architecture
- Anomaly detection
- Predictive maintenance
- Root-cause analysis chains
- Runbook retrieval
- Operational memory
- Automated remediation recommendations

---

## Product Features

- Organization/workspace support
- Role-based access control
- Admin dashboard
- Notification preferences
- Email or Slack alert delivery
- Exportable reports
- Saved investigation templates

---

## Observability

- Historical fleet-wide trends
- Device comparison charts
- Alert timeline
- Incident timeline
- Device dependency graph
- Geographic device map

---

## Deployment

Possible deployment path:

```text
Flask App
  ↓
Gunicorn / eventlet
  ↓
PostgreSQL
  ↓
Cloud platform
  ↓
Custom domain
```

---

## Long-Term Vision

IoT Ops Agent can evolve from a simulated AI operations dashboard into a real operational copilot for IoT infrastructure.

Potential production use cases:

- monitoring device fleets
- diagnosing connectivity issues
- analyzing telemetry trends
- prioritizing incidents
- supporting operators with AI-assisted investigations