# Company Operational Data Discovery

This project keeps company operational data separate from app-owned data.

- Supabase/Postgres stores IoT Ops Agent app data: users, chats, messages,
  prompts, Telegram identities, and source policy.
- Company MongoDB is operational evidence and is reached through the MCP
  server only.
- Flask must not hold `COMPANY_MONGODB_URI` or direct Grafana/Loki/Prometheus
  credentials.

## MCP Boundary

```text
Flask app
  -> MCP_SERVER_URL + MCP_BEARER_KEY
  -> MCP server
  -> company MongoDB / Loki / Grafana / Prometheus
```

Company MongoDB credentials belong in `mcp_server/.env`:

```env
COMPANY_MONGODB_URI=replace_me
COMPANY_MONGO_ALLOWED_NAMESPACES=authorization.IDENTITY,subNNotif.AE,subNNotif.SUB,datamgmt.CNT,datamgmt.CIN,datamgmt.DEVICE_TELEMETRY,datamgmt.RULE,devicemgmt.NODE,orchestration.URI_MAPPER
```

The Flask `.env` only needs:

```env
COMPANY_DATA_ACCESS_MODE=mcp
MCP_SERVER_URL=http://127.0.0.1:8000/mcp
MCP_BEARER_KEY=replace_me
```

## Mongo Read Guardrails

MCP Mongo tools use the read proxy in `mcp_server/services/company_mongo_proxy.py`.
The proxy exposes bounded read operations only:

- `find`
- database/collection discovery when allowed
- collection statistics when allowed

It does not expose insert, update, delete, aggregation, or arbitrary database
commands. Queries always apply limits and `maxTimeMS`; unsafe operators such
as `$where`, `$function`, `$out`, and `$merge` are rejected.

Database and collection access is restricted by
`COMPANY_MONGO_ALLOWED_NAMESPACES`. A syntactically valid MongoDB namespace is
not enough by itself.

## Unified OneM2M Read Model

The company read model is built from bounded evidence in these resource
families:

```text
devicemgmt.NODE.childDeviceInfoEntities  -> device inventory
authorization.IDENTITY                  -> identity metadata
datamgmt.CNT                            -> container ownership
datamgmt.CIN                            -> latest command/telemetry CINs
datamgmt.DEVICE_TELEMETRY               -> metric names and units
datamgmt.RULE                           -> rule references
subNNotif.AE                            -> application entity resources
subNNotif.SUB                           -> subscription resources
orchestration.URI_MAPPER                -> URI/resource mapping
```

Devices are joined by normalized platform identifiers or names. Telemetry is
assigned to a device only when DB/log evidence supports the relationship.
Unresolved telemetry is counted but not guessed.

## Source Behavior

When company data is selected and MCP evidence is reachable, the app reports
company source metadata. If MCP or company data is unavailable, the app must
return an explicit `simulator_fallback` state. Fallback data must never be
presented as company evidence.

## Discovery Checklist

Before treating a company scenario as production-ready, confirm:

- allowed MongoDB namespaces
- required OneM2M resource ownership for `IDENTITY`, `AE`, `CNT`, `CIN`,
  `SUBSCRIPTION`, and `URI_MAPPER`
- authoritative timestamp fields
- tenant/site ownership rules
- service names that may be searched in Loki
- official KPI/rule owners and thresholds
- Prometheus metric names and required labels
- Grafana datasource used by MCP queries

## Verification

Run MCP-backed workflow tests:

```bash
.venv/bin/python -m unittest tests.test_ioa_v3_workflow -v
```

Run a platform prompt such as `/resources`, `/telemetry`, or `/cmd` with a
known device ID and verify the reasoning trace shows MCP Mongo/Loki tool
execution.
