# Company DB Discovery

This project keeps the company operational DB separate from the app-data DB.

`SUPABASE_DB_URL` stores IoT Ops Agent platform data such as users, chats, messages, and prompts.

`COMPANY_DB_URL` or `COMPANY_MONGODB_URI` is reserved for the real operational
data source. The current unified device adapter uses MongoDB; Company Postgres
remains a schema-probing path.

## Environment

Use a read-only database user.

```env
COMPANY_DB_URL=postgresql://readonly_user:[PASSWORD]@company-db-host:5432/company_db
COMPANY_MONGODB_URI=mongodb://readonly_user:[PASSWORD]@company-mongo-host:27017/?authSource=admin
COMPANY_MONGODB_DB=
COMPANY_MONGO_ALLOWED_NAMESPACES=devicemgmt.NODE,authorization.IDENTITY,datamgmt.CNT,datamgmt.CIN,datamgmt.DEVICE_TELEMETRY,datamgmt.RULE
COMPANY_DB_CONNECT_TIMEOUT_SECONDS=5
COMPANY_DB_STATEMENT_TIMEOUT_MS=5000
COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS=120
COMPANY_MONGO_PROXY_RATE_LIMIT_WINDOW_SECONDS=60
```

Do not commit real connection strings. Set them in `.env` locally or Render environment variables only.

If both Postgres and MongoDB variables are present, the probe uses MongoDB first.

## Company MongoDB Read Proxy

All Company MongoDB reads pass through `services/company_mongo_proxy.py`.
The proxy exposes only bounded read operations:

- `find`
- database and collection discovery
- collection statistics

It does not expose insert, update, delete, aggregation, or arbitrary database
commands. Queries always apply a document limit and `maxTimeMS`; server-side
JavaScript and write-stage operators such as `$where`, `$function`, `$out`,
and `$merge` are rejected.

Database and collection access is also restricted by
`COMPANY_MONGO_ALLOWED_NAMESPACES`. Discovery results are filtered through the
same allowlist. A valid MongoDB identifier is not sufficient by itself.

The proxy rate limit is process-local and counts MongoDB read operations by
caller. API reads and LLM tool reads use separate caller keys. One unified
device-model load currently performs six bounded reads.
For a multi-instance deployment, enforce an additional shared rate limit at
the API gateway or replace the in-memory limiter with Redis.

The proxy is an application guardrail, not a substitute for MongoDB
authorization. `COMPANY_MONGODB_URI` must use a MongoDB account with the
built-in `read` role only on the required databases. Do not grant `readWrite`,
`dbAdmin`, or cluster administration roles to the application account.

## Probe Schema

```bash
python -m scripts.probe_company_db --table-limit 20
```

If no company DB URL is present or the company DB is unavailable, the script returns a simulator fallback snapshot.

## Preview A Table

Use low limits only:

```bash
python -m scripts.probe_company_db --preview public.devices --preview-limit 5
```

For MongoDB, use `database.collection`:

```bash
python -m scripts.probe_company_db --preview operations.devices --preview-limit 5
```

To inspect MongoDB field paths without printing values:

```bash
python -m scripts.probe_company_db --inspect datamgmt.CNT --preview-limit 10
python -m scripts.probe_company_db --inspect datamgmt.CIN --preview-limit 10
```

To inspect a JSON payload field such as oneM2M `CIN.con` without printing
payload values:

```bash
python -m scripts.probe_company_db --inspect-payload datamgmt.CIN --payload-field con --preview-limit 20
```

Guardrails:

- read-only transaction
- read-only Company MongoDB proxy
- Company MongoDB operation rate limit
- statement timeout
- table and row limits
- MongoDB `maxTimeMS`
- identifier validation
- long text truncation

## Tool Direction

Do not expose a generic SQL tool to the LLM.

Prefer narrow operational tools:

```text
get_device_status(device_id)
get_gateway_health(gateway_id)
get_active_alarms(site_id)
get_recent_device_logs(device_id, time_range)
```

Each tool should apply explicit filters, limits, and output shaping before data reaches the model.

## Platform Source Switch

The Devices screen can switch between:

```text
Simulator
Company DB
```

When Company DB is selected and reachable, the backend reports:

```json
{
  "source": "company_mongodb",
  "rules_status": "provisional_poc",
  "official_rules_status": "discovered_unmapped"
}
```

Warning and critical counts come only from the isolated `company-poc-v1`
fallback ruleset and are labeled non-official. Discovered company rules are
not executed or reinterpreted.

If the company database is unavailable, the API returns an explicit simulator fallback state instead of silently pretending the data is real.

Manual threshold prompts are supported as evidence scans over raw payloads, not official company alerts.

## Unified Device And Telemetry Read Model

The company preview now builds a bounded, read-only model from:

```text
devicemgmt.NODE.childDeviceInfoEntities  -> device inventory
authorization.IDENTITY                  -> identity metadata
datamgmt.CNT                            -> container ownership
datamgmt.CIN.con                        -> status and telemetry values
datamgmt.DEVICE_TELEMETRY               -> metric names and units
datamgmt.RULE                           -> device rule references
```

Devices are joined by normalized platform identifiers or names. Telemetry
without an explicit identity is joined only when its `CIN`/`CNT` ownership
resolves to a known device. Unresolved telemetry is counted but never assigned
by guesswork. Command content is counted separately and excluded from telemetry
history.

`CIN.con` remains application-defined content. The adapter displays primitive
measurement and event fields that actually exist, and uses a unit only when the
telemetry catalog provides one unambiguous value.

The database contains company rules in `datamgmt.RULE`. The PoC exposes rule
counts per matched device but does not execute or reinterpret their business
semantics. Raw connection status is telemetry evidence, not alert severity.

Before this becomes an operational dashboard, confirm:

- which timestamp represents event time versus ingestion time
- tenant and site ownership rules
- rule status, severity, trigger, and filter enum semantics
- whether Grafana remains the authoritative alert execution source

Until that contract exists, official company rule evaluation remains pending.
Any warning or critical count shown by the PoC comes only from the provisional
local ruleset described below.

## Provisional PoC Alert Flow

For demonstrations, the platform runs a separate fallback ruleset named
`company-poc-v1`. These findings are deliberately isolated from the discovered
company rules and are always marked `official: false`.

Current provisional rules:

- explicit payload status `disconnected` or `offline` -> critical
- temperature fields `temp`, `temperature`, or `NhietDo` >= 50 -> warning
- the same temperature fields >= 70 -> critical
- RSSI <= -70 -> warning
- RSSI <= -85 -> critical

Every finding includes the rule ID, device, raw evidence, threshold, source
collection, ruleset version, and disclaimer. Temperature units and business
thresholds still require company confirmation.

The intended end-to-end demo flow is:

```text
Company prompt
  -> source resolver chooses Company DB or simulator fallback
  -> selected web runtime receives bounded company evidence
  -> Custom Python or LangGraph selects a focused read-only tool
  -> bounded unified device/telemetry read model
  -> provisional PoC rule evaluation
  -> evidence-backed chat answer and Alerts UI
  -> explicit handoff gap to official company rules or Grafana
```

LangChain, n8n, and Dify receive bounded company context packaged by Flask.
Telegram uses IOA v3 Ops Graph and follows its remembered or default source.
