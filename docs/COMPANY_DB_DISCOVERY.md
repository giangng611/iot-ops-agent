# Company DB Discovery

This project keeps the company operational DB separate from the app-data DB.

`SUPABASE_DB_URL` stores IoT Ops Agent platform data such as users, chats, messages, and prompts.

`COMPANY_DB_URL` or `COMPANY_MONGODB_URI` is reserved for the real operational data source used by LangGraph tools.

## Environment

Use a read-only database user.

```env
COMPANY_DB_URL=postgresql://readonly_user:[PASSWORD]@company-db-host:5432/company_db
COMPANY_MONGODB_URI=mongodb://readonly_user:[PASSWORD]@company-mongo-host:27017/?authSource=admin
COMPANY_MONGODB_DB=
COMPANY_DB_CONNECT_TIMEOUT_SECONDS=5
COMPANY_DB_STATEMENT_TIMEOUT_MS=5000
```

Do not commit real connection strings. Set them in `.env` locally or Render environment variables only.

If both Postgres and MongoDB variables are present, the probe uses MongoDB first.

## Probe Schema

```bash
python3 scripts/probe_company_db.py --table-limit 20
```

If no company DB URL is present or the company DB is unavailable, the script returns a simulator fallback snapshot.

## Preview A Table

Use low limits only:

```bash
python3 scripts/probe_company_db.py --preview public.devices --preview-limit 5
```

For MongoDB, use `database.collection`:

```bash
python3 scripts/probe_company_db.py --preview operations.devices --preview-limit 5
```

To inspect MongoDB field paths without printing values:

```bash
python3 scripts/probe_company_db.py --inspect datamgmt.CNT --preview-limit 10
python3 scripts/probe_company_db.py --inspect datamgmt.CIN --preview-limit 10
```

To inspect a JSON payload field such as oneM2M `CIN.con` without printing
payload values:

```bash
python3 scripts/probe_company_db.py --inspect-payload datamgmt.CIN --payload-field con --preview-limit 20
```

Guardrails:

- read-only transaction
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

When Company DB is selected, the backend reads raw company MongoDB operational records and marks:

```json
{
  "rules_status": "not_configured"
}
```

The Alerts screen must not derive warning or critical alerts from raw company records until approved business rules or Grafana tools are available.

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

Until that contract exists, the platform reports rules as discovered with
evaluation pending and does not produce warning or critical counts.
