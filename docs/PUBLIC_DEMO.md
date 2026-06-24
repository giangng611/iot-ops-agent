# Public Fallback Demo

The public demo version of IoT Ops Agent should show the architecture and user
experience without depending on company databases, internal Grafana links,
credentials, or company-owned rule semantics.

## Demo Boundary

The public GitHub version may include:

* simulator or fallback telemetry
* local SQLite/MongoDB setup instructions
* mock Grafana Dashboard Client responses
* generic n8n workflow definitions
* IOA v3 Ops Graph policy and reasoning traces
* web UI screenshots that do not expose company data
* anonymized sample prompts and generic operational scenarios

The public GitHub version must not include:

* `.env` files or real credentials
* Company DB connection strings, hostnames, dumps, logs, or screenshots
* private Grafana dashboard URLs, tokens, datasource names, or query details
* company-specific KPI thresholds unless explicitly approved for publication
* internal usernames, Telegram IDs, access codes, or private webhook secrets

## Recommended Local Demo Stack

Run the demo with mock/fallback systems:

```bash
python3 scripts/mock_grafana_dashboard_client.py --port 5050
```

```bash
N8N_PORT=5679 n8n
```

```bash
export N8N_V3_WEBHOOK_URL=http://localhost:5679/webhook/grafana-ops-gateway
export GRAFANA_DASHBOARD_CLIENT_URL=http://127.0.0.1:5050
export IOA_V3_ENABLE_KPI_RULES=false
```

The public demo can still show:

* source-aware answers
* policy-gated tool routing
* n8n workflow execution
* reasoning traces
* alert-style summaries
* simulator fallback behavior

## Internal Pilot Split

Keep the company-connected version in the company GitLab project. That version
can use approved environment variables for Company DB, internal Grafana, and
official rule mapping.

The public demo and internal pilot should share the same architecture, but only
the internal pilot should know how to reach company systems.

## Pre-publication Checklist

Before pushing a public demo repository:

* search for private hostnames, URLs, tokens, usernames, and access codes
* remove generated outputs that contain company data
* replace real Grafana screenshots with mock or generic screenshots
* keep `.env.example`, but never commit `.env`
* confirm the repository history does not contain removed secrets
* document that company integrations are represented by mock adapters
