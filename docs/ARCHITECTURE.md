# Architecture

IoT Ops Agent is a Flask and Socket.IO application with company and simulator
data sources, multiple agent runtimes, an IOA v3 policy workflow layer,
MCP-backed operational evidence collection, and a separate relational app-data
store.

## High-Level Flow

```text
Simulator telemetry ─────────────────────────────────────────┐
                                                             |
Web UI / Telegram -> Flask routes -> source resolver -> IOA runtimes
                                                             |
                                                             v
                                  answer + reasoning trace + runtime metadata

IOA v3 Ops Graph -> MCP Server -> MongoDB / Loki / Prometheus
                        |
                        └─ bearer auth, rate limit, audit log

App data -> Supabase/Postgres -> fail-closed by default
Simulator telemetry -> MongoDB when enabled, SQLite only as fallback/debug
```

The storage systems are parallel responsibilities. MongoDB telemetry does not
flow through Supabase/Postgres or SQLite app-data tables.

## Operational Data Sources

### Simulator

`simulator.py` and the optional embedded telemetry loop generate CPU, memory,
heartbeat delay, status, logs, and simulator alarm metadata.

`storage/telemetry_store.py` routes simulator telemetry reads and writes. The
preferred local/runtime telemetry store is MongoDB when simulator telemetry is
enabled:

* `TELEMETRY_WRITE_BACKEND=mongodb` writes MongoDB.
* `READ_TELEMETRY_FROM_MONGO=true` selects MongoDB reads.
* `TELEMETRY_WRITE_BACKEND=dual` writes SQLite and MongoDB during migration or
  verification.
* `TELEMETRY_WRITE_BACKEND=sqlite` is a last-resort fallback/debug mode.

### Company MongoDB Through MCP

Company operational data is reached through the separate `mcp_server/`
process. The Flask app is an MCP client and should not hold the real
`COMPANY_MONGODB_URI`. It only needs `COMPANY_DATA_ACCESS_MODE=mcp`,
`MCP_SERVER_URL`, and `MCP_BEARER_KEY`.

Inside the MCP server, `mcp_server/services/company_mongo_proxy.py` permits
bounded reads only, validates database and collection names, blocks unsafe
operators, applies `maxTimeMS`, and rate-limits operations by caller.

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

### Loki / Grafana / Prometheus Evidence Through MCP

IOA v3 collects operational logs and metrics through MCP tools:

```text
grafana_logs          -> loki_query_range
grafana_queue_*       -> grafana_query / grafana_query_range
grafana_emqx_*        -> grafana_query_range
grafana_k8s_*         -> grafana_query
```

The MCP server owns `GRAFANA_URL`, `GRAFANA_USERNAME`/`GRAFANA_PASSWORD`, or
`GRAFANA_API_KEY`. The Flask app does not store Grafana/Loki/Prometheus
credentials. Grafana dashboard UI URLs are human references for KPI mapping and
review, not direct tool-call targets.

The older n8n Grafana gateway can still be used for IOA v2/runtime comparison,
but it is not the primary evidence path for IOA v3 runbook scenarios.

## App Data

Users, chats, messages, prompts, Telegram identities, and data-source policies
are routed by `storage/relational_store.py`:

* `APP_DB_BACKEND=supabase` uses Supabase/Postgres.
* `APP_DB_FALLBACK_ENABLED=false` fails closed when Postgres is unavailable.
* `APP_DB_FALLBACK_ENABLED=true` is only for explicit degraded local fallback.
* `APP_DB_BACKEND=sqlite` exists for local fallback/debug only, not normal
  company runtime.

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
source permissions, params, and execution budget before any MCP, Company DB, or
legacy Grafana workflow runs.

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
* read-only Company MongoDB credentials isolated in the MCP server
* Flask-side MCP bearer authentication for company operational evidence
* bounded query limits, timeouts, identifier validation, and blocked operators
* process-local Company MongoDB proxy rate limiting
* Telegram secret-token validation and optional sender allowlist

Production work still includes shared/distributed rate limiting, RBAC,
centralized audit storage, official company rule integration, and approval
gates for any future write action.

## MCP Server (peer service)

`mcp_server/` is a separate, independently deployed process — not part of the
Flask app above — that exposes read-only MongoDB, Grafana Loki, and
Grafana/Prometheus tools over the MCP protocol (Streamable HTTP). It is the
sole holder of the real Mongo/Loki/Grafana credentials; callers authenticate
only with a bearer key scoped to the MCP server itself, verified with
`hmac.compare_digest` before any tool runs (`mcp_server/auth.py`). The Mongo
tools use the MCP server's copy of the company Mongo guardrail with
namespace allowlists, blocked operators, rate limiting, and audit logs. See
[MCP Server Integration](MCP_SERVER_INTEGRATION.md),
[MCP Server Usage](MCP_SERVER_USAGE.md), and
[MCP Server Deployment](MCP_SERVER_DEPLOYMENT.md).
