# Architecture

IoT Ops Agent is a Flask and Socket.IO application with simulator/company data
sources, multiple agent runtimes, an IOA v3 policy workflow layer, optional
n8n/Grafana evidence collection, and a separate relational app-data store.

## High-Level Flow

```text
Simulator telemetry ───────────────────────────────┐
                                                   |
Company MongoDB -> read-only policy proxy ─────────┤
                                                   v
Web UI / Telegram -> Flask routes -> source resolver -> agent runtime
                                                   |
                                                   v
                                  answer + reasoning trace + runtime metadata

Grafana Dashboard Client API -> n8n gateway -> IOA v3 Ops Graph

App data -> Supabase/Postgres -> fail-closed by default
```

The storage systems are parallel responsibilities. MongoDB telemetry does not
flow through Supabase/Postgres or SQLite app-data tables.

## Operational Data Sources

### Simulator

`simulator.py` and the optional embedded telemetry loop generate CPU, memory,
heartbeat delay, status, logs, and simulator alarm metadata.

`storage/telemetry_store.py` routes simulator telemetry reads and writes:

* `TELEMETRY_WRITE_BACKEND=sqlite` uses SQLite.
* `TELEMETRY_WRITE_BACKEND=dual` writes SQLite and MongoDB.
* `TELEMETRY_WRITE_BACKEND=mongodb` writes MongoDB.
* `READ_TELEMETRY_FROM_MONGO=true` selects MongoDB reads with SQLite fallback.

### Company MongoDB

Company data is a separate source configured with `COMPANY_MONGODB_URI`.
`services/company_mongo_proxy.py` permits bounded reads only, validates
database and collection names, blocks unsafe operators, applies `maxTimeMS`,
and rate-limits operations by caller.

`services/company_data_service.py` builds a unified read model from:

```text
devicemgmt.NODE.childDeviceInfoEntities
authorization.IDENTITY
datamgmt.CNT
datamgmt.CIN
datamgmt.DEVICE_TELEMETRY
datamgmt.RULE
```

The Company DB adapter exposes inventory, telemetry coverage, device lookup,
disconnected-device, rule-readiness, provisional-alert, and numeric-threshold
contexts. It never exposes arbitrary MongoDB commands to an LLM.

If Company MongoDB cannot be read, the source resolver reports
`simulator_fallback`; the UI and agent use simulator data instead of presenting
fallback records as company data.

### Grafana / Observability Evidence

IOA v3 can collect infrastructure and service evidence through n8n. The backend
sends one approved workflow, one approved path, and filtered params to the n8n
gateway. n8n then calls the configured Grafana Dashboard Client API and returns
normalized JSON evidence.

The configured value `GRAFANA_DASHBOARD_CLIENT_URL` must point at an API
adapter or local mock client. Grafana dashboard UI URLs are human references for
KPI mapping and review, not direct tool-call targets.

## App Data

Users, chats, messages, prompts, Telegram identities, and data-source policies are routed by
`storage/relational_store.py`:

* `APP_DB_BACKEND=sqlite` uses local SQLite.
* `APP_DB_BACKEND=supabase` uses Supabase/Postgres.
* `APP_DB_FALLBACK_ENABLED=false` fails closed when Postgres is unavailable.
* `APP_DB_FALLBACK_ENABLED=true` is only for explicit local/demo fallback.

The browser does not query Supabase directly. Flask uses a server-side Postgres
connection, and the schema revokes direct table access from Supabase client
roles.

## Flask Application

`app.py` owns application wiring, agent construction, blueprint registration,
Socket.IO setup, database initialization, and the embedded telemetry task.

Service and route responsibilities include:

* `routes/diagnose_routes.py`: synchronous and SSE diagnosis endpoints, source
  resolution, validation, and request rate limiting.
* `routes/telemetry_routes.py`: device APIs, telemetry history, and per-session
  Simulator / Company DB selection.
* `routes/telegram_routes.py`: Telegram webhook validation and background
  processing.
* `services/diagnose_service.py`: context packaging for n8n and Dify.
* `services/telegram_service.py`: Telegram commands, deduplication, identity
  mapping, RBAC/source authorization, chat persistence, and LangGraph
  streaming.

## Agent Runtimes

The web workspace supports:

* `IOA v1 · Custom Python`
* `IOA v2 · Custom Python`
* `IOA v2 · LangChain`
* `IOA v2 · LangGraph`
* `IOA v2 · n8n`
* `IOA v2 · Dify`
* `IOA v3 · Ops Graph`

When Company DB is active, every web runtime receives company operational
evidence. If the source is unavailable, every runtime receives simulator
fallback context.

The IOA v2 custom runtime uses a visible read-only Company DB tool step after
verifying the resolved snapshot. LangGraph selects company-specific tools
directly. LangChain, n8n, and Dify receive bounded company context packaged by
Flask.

Telegram currently uses the in-process `IOA v3 · Ops Graph` runtime. Each
Telegram sender must be mapped in `telegram_identities` before the runtime can
execute approved workflows. The mapped IoT Ops Agent user owns the saved chat
history and source selection. A request is rejected before agent execution when
the identity is unmapped, inactive, outside `TELEGRAM_ALLOWED_USER_IDS`, or not
allowed to use the selected data source.

`IOA v3 · Ops Graph` uses a hybrid planner. The semantic planner proposes one
or more approved workflows from the user's request. A deterministic taxonomy
remains as a fallback for invalid planner output, low-confidence plans, or
disabled semantic planning. A policy verifier still checks tool allowlists,
source permissions, params, and execution budget before any Company DB or
Grafana workflow runs.

## Public Demo Boundary

The public demo path uses simulator telemetry and mock Grafana evidence. It can
show the same UI, reasoning traces, source selection, IOA v3 routing, and n8n
workflow shape without storing company credentials, private dashboard URLs, or
company-specific KPI semantics.

## Reasoning Trace

`/api/diagnose-stream` emits SSE events:

```text
thought
observation
final
error
```

The frontend keeps live and historical trace state separate. Workflow status
is reset before a new request is exposed in the UI, so completed nodes from a
previous answer do not leak into a running trace.

## Realtime Updates

Flask-SocketIO broadcasts simulator `device_update` events. Company data is
read on request and is not overwritten by simulator socket events while the
Company DB source is selected.

Telegram processing can emit:

```text
telegram_chat_started
telegram_reasoning_event
telegram_chat_completed
telegram_chat_failed
```

These events synchronize Telegram-originated runs with the web workspace when
the Telegram account is mapped to an IoT Ops Agent user.

## Security Boundary

Current guardrails include:

* authenticated web APIs
* access-code protected registration
* diagnosis message-size and per-process rate limits
* read-only Company MongoDB credentials and proxy operations
* bounded query limits, timeouts, identifier validation, and blocked operators
* process-local Company MongoDB proxy rate limiting
* Telegram secret-token validation and optional sender allowlist

Production work still includes shared/distributed rate limiting, RBAC,
centralized audit storage, official company rule integration, and approval
gates for any future write action.

## MCP Server (peer service)

`mcp_server/` is a separate, independently deployed process — not part of
the Flask app above — that exposes read-only MongoDB, Grafana Loki, and
(optionally) Grafana/Prometheus tools over the MCP protocol (Streamable
HTTP) for external agents over the public Internet. It is the sole holder
of the real Mongo/Loki/Grafana credentials; external callers authenticate
only with a bearer key scoped to the MCP server itself, verified with
`hmac.compare_digest` before any tool runs (`mcp_server/auth.py`). The Mongo
tools reuse `services/company_mongo_proxy.py` directly rather than
duplicating its allowlist/rate-limit/audit logic. See
[docs/MCP_SERVER_PLAN.md](MCP_SERVER_PLAN.md) and
[docs/MCP_SERVER_DEPLOYMENT.md](MCP_SERVER_DEPLOYMENT.md).
