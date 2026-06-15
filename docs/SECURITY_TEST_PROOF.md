# Security Test Evidence Report

Assessment date: June 15, 2026

## 1. Scope

This assessment covers:

- Personal application databases: Supabase/Postgres and local MongoDB.
- Flask APIs for authentication, chats, prompts, telemetry, storage, and
  diagnosis.
- Company database access proxies through isolated unit tests and mocks.
- Telegram webhook authentication.

This assessment does not include:

- Destructive testing against the live company database.
- Infrastructure, operating system, GitLab, or Supabase dashboard penetration
  testing.
- A third-party penetration test or formal compliance certification.

## 2. Executive Summary

Current result: **Conditional pass for the personal databases and application
security controls.**

The assessment verified that:

- Common SQL injection payloads cannot bypass authentication or destroy tables.
- Dangerous MongoDB query operators are rejected by the company database
  proxy.
- Anonymous clients cannot read the local MongoDB instance.
- The MongoDB runtime account is restricted to four required actions on one
  collection.
- Users cannot read, modify, or delete another user's chats or prompts.
- Sensitive API routes require an authenticated session.
- Repeated login attempts and MongoDB read requests are rate-limited.
- Database queries use hard result limits and execution timeouts.
- API responses do not expose database credentials, private hostnames,
  connection strings, or provider keys.
- Supabase Row Level Security is enabled and browser-facing roles have no
  direct CRUD privileges.
- Telegram requests with an invalid webhook secret are rejected.

Latest automated result:

```text
86 tests passed
```

Latest live verification:

```text
MongoDB permission checker: secure=true
Supabase RLS checker: secure=true
```

## 3. Simulated Attack Scenarios

### 3.1 SQL Injection Through Authentication and User Input

Representative payload:

```text
' OR 1=1; DROP TABLE users; --
```

Attack objectives:

- Bypass username and password validation.
- Append a destructive SQL statement.
- Cause user input to execute as SQL.

Observed result:

- The login endpoint returned `401`.
- The payload was stored as ordinary text when submitted as prompt content.
- The `users` table remained available.
- The legitimate account continued to authenticate successfully.

Controls:

- SQLite statements use `?` placeholders.
- Postgres statements use `%s` placeholders.
- User-provided values are not concatenated into SQL statements.

Evidence:

- `test_sql_injection_payloads_do_not_bypass_login_or_damage_tables`
- `test_postgres_preview_rejects_identifier_injection_before_connecting`
- `test_read_only_guardrails_are_applied_with_parameterized_timeout`

### 3.2 SQL Identifier Injection Against Company Postgres Preview

Representative payloads:

```text
public; drop schema public cascade; --
devices"; drop table users; --
```

Observed result:

- Invalid schema and table names raised `ValueError`.
- Validation occurred before a database connection was opened.

Additional controls:

- Schema and table names must match an identifier allowlist.
- Company Postgres transactions are explicitly set to read-only.
- Statement timeouts are applied through parameterized statements.

### 3.3 MongoDB Server-Side JavaScript Injection

Representative payload:

```javascript
{"$where": "function () { return true; }"}
```

Observed result:

- The proxy rejected the query before it reached MongoDB.

Evidence:

- `test_find_rejects_server_side_javascript_operator`

### 3.4 MongoDB Operator Injection and Expensive Queries

Representative payloads:

```javascript
{"name": {"$regex": ".*"}}
{"$expr": {"$eq": ["$status", "critical"]}}
{"location": {"$near": [0, 0]}}
```

Blocked operators include:

- `$where`
- `$function`
- `$accumulator`
- `$expr`
- `$regex`
- `$text`
- `$near`
- `$nearSphere`
- `$geoNear`
- `$jsonSchema`
- `$merge`
- `$out`

Additional controls:

- Invalid sort fields and directions are rejected.
- Command-like or malformed namespaces are rejected.
- Result limits are clamped.
- Server-side execution timeouts are applied.

Evidence:

- `test_find_rejects_expensive_query_operators`
- `test_find_rejects_invalid_namespace_sort_and_limit`
- `test_find_applies_timeout_sort_and_hard_limit`

### 3.5 Unauthenticated MongoDB Access

The live local MongoDB instance rejected an anonymous read:

```text
Command find requires authentication
```

Authorization is enabled:

```yaml
security:
  authorization: enabled
```

Runtime identity:

```text
iot_ops_runtime@iot_ops_agent
```

Granted actions:

```text
find
insert
listIndexes
update
```

Allowed resource:

```text
iot_ops_agent.telemetry
```

The runtime account does not have administrative or destructive actions such
as:

- `remove`
- `dropCollection`
- `dropDatabase`
- `createIndex`
- `userAdmin`
- `dbAdmin`
- `root`

The runtime account requires `insert` and `update` because the simulator writes
telemetry and the backfill process uses upserts. Index administration uses the
separate `MONGODB_ADMIN_URI` credential.

Evidence:

- `test_accepts_authenticated_collection_scoped_runtime_actions`
- `test_rejects_anonymous_or_overprivileged_connections`
- `scripts/check_mongodb_permissions.py`

### 3.6 MongoDB Read API Abuse

Controls:

- An authenticated Flask session is required.
- Requests are rate-limited per user.
- The default limit is 60 requests per 60 seconds.
- Exceeded limits return `429` and a `Retry-After` header.
- One user's quota does not consume another user's quota.
- A request can return no more than 100 records.

The company MongoDB proxy separately enforces:

- 120 operations per 60 seconds by default.
- Independent counters per actor and operation.

Evidence:

- `test_mongo_read_rate_limit_is_enforced_per_user`
- `test_sliding_window_rate_limiter_rejects_excess_reads`
- `test_rate_limit_environment_is_read_at_request_time`
- `test_rate_limits_are_isolated_by_actor`
- `test_mongo_routes_clamp_read_limits_and_disallow_index_writes`

### 3.7 Password Guessing and Brute Force

Controls:

- The default limit is 10 attempts per 300 seconds.
- The rate-limit key includes the source IP address and normalized username.
- Exceeded limits return `429` and a `Retry-After` header.
- A successful login clears the counter for that identity.

Evidence:

- `test_login_rate_limit_blocks_repeated_password_guessing`

### 3.8 Cross-User Data Access

The tests attempt to:

- Read another user's chat messages.
- Add a message to another user's chat.
- Delete another user's chat.
- Modify another user's prompt.
- Delete another user's prompt.

Observed result:

- The endpoints returned `404`.
- The owner's data remained unchanged.

Evidence:

- `test_chat_messages_require_owner`
- `test_prompt_routes_reject_cross_user_update_and_delete`
- `test_prompt_crud_routes_use_authenticated_user`

### 3.9 Unauthenticated Access to Sensitive APIs

Protected route groups include:

- Diagnosis and diagnosis streaming.
- Data-source selection.
- Device and telemetry data.
- MongoDB health, indexes, devices, and history.
- Storage status.
- Chats and messages.
- Prompts.
- Profile usage.

Observed result:

- All unauthenticated requests returned `401`.

Evidence:

- `test_sensitive_routes_require_login`

### 3.10 Unauthorized Index Administration

Previously, an authenticated user could call:

```text
POST /api/mongo/telemetry/indexes
```

After hardening:

- The endpoint only supports `GET`.
- `POST` returns `405`.
- Index creation uses a separate administrative script and credential.

Evidence:

- `test_mongo_routes_clamp_read_limits_and_disallow_index_writes`

### 3.11 Sensitive Information Disclosure Through Errors

Simulated exceptions contained values such as:

```text
mongodb://admin:super-secret@internal-db.example:27017
postgresql://admin:db-secret@private-db.internal/app
api_key=secret-key
```

Observed result:

- Responses did not contain passwords or API keys.
- Responses did not contain internal hostnames.
- Storage status exposes only the exception type, such as `RuntimeError`.
- Company database fallback responses use a generic failure message.
- Synchronous and streaming diagnosis responses use a generic runtime error.

Evidence:

- `test_mongo_routes_do_not_expose_database_exception_details`
- `test_company_fallback_does_not_expose_database_exception_details`
- `test_storage_status_does_not_expose_database_exception_details`
- `test_diagnose_responses_do_not_expose_runtime_exception_details`

### 3.12 Direct Supabase Access by Browser Roles

The live checker verified that:

- RLS is enabled on `users`.
- RLS is enabled on `chats`.
- RLS is enabled on `messages`.
- RLS is enabled on `prompts`.
- The `anon` role has no SELECT, INSERT, UPDATE, or DELETE privileges.
- The `authenticated` role has no SELECT, INSERT, UPDATE, or DELETE
  privileges.

Verification command:

```bash
python3 scripts/check_supabase_rls.py
```

Observed result:

```text
secure=true
missing_tables=[]
```

### 3.13 Long-Running Queries, Locks, and Database Outages

Verified controls:

- Postgres connection timeout.
- Statement timeout.
- Lock timeout.
- Timeout reapplication after a pooled connection is checked out.
- No repeated retry after pool timeout.
- Circuit breaker with SQLite fallback.
- Optional fail-closed behavior when fallback is disabled.

Evidence:

- `test_postgres_connections_apply_query_timeouts`
- `test_postgres_timeouts_are_applied_after_pool_checkout`
- `test_postgres_pool_timeout_falls_back_without_retry`
- `test_postgres_circuit_breaker_uses_sqlite_after_failure`
- `test_supabase_error_raises_when_fallback_disabled`
- `test_storage_status_reports_unavailable_when_fallback_disabled`

### 3.14 Diagnosis Request Abuse

Verified controls:

- Oversized messages return `413`.
- Requests exceeding the configured quota return `429`.
- Rate-limit responses include `Retry-After`.

Evidence:

- `test_diagnose_limits_are_enforced`

### 3.15 Forged Telegram Webhooks

Verified controls:

- An invalid webhook secret returns `403`.
- Duplicate updates are not processed twice.
- Background failures do not expose stack traces to the UI.

Evidence:

- `test_telegram_webhook_rejects_invalid_secret`
- `test_telegram_duplicate_update_is_answered_once`
- `test_telegram_background_failure_notifies_ui`

## 4. Test Method and Data Safety

Attack-oriented unit and integration tests use:

- SQLite databases created in temporary directories.
- Fake or mocked MongoDB clients.
- Mocked Postgres cursors and connections.

This allows destructive-looking payloads to be tested without sending
destructive operations to a live database.

Live verification is limited to:

- Reading Supabase system catalogs and privilege metadata.
- Reading MongoDB connection, role, and action metadata.
- Reading a small telemetry sample.
- Confirming that an anonymous MongoDB read is rejected.

The following operations were not executed against a live database:

- `DROP TABLE`
- `DROP DATABASE`
- `DELETE`
- `remove`
- Destructive `update`
- High-volume load or stress testing

## 5. Test Suite Classification

Current suite: 86 tests.

Direct security coverage:

- Authentication and protected routes.
- SQL injection and identifier injection.
- MongoDB query and operator injection.
- Database role and privilege allowlists.
- Cross-user ownership.
- Rate limiting and request-size controls.
- Secret and error disclosure.
- Supabase RLS.
- Telegram webhook authentication.
- Timeouts, circuit breakers, and fallback behavior.

Related safety and observability coverage:

- Agents use company data only when the company source is active.
- Company database outages fall back to the simulator.
- Agents collect tool evidence before producing conclusions.
- Company rule results retain provenance.
- Duplicate Telegram updates are deduplicated.

Full test command:

```bash
python3 -m unittest discover -s tests -v
```

## 6. Known Limitations and Residual Risks

### 6.1 Process-Local Rate Limiting

Rate-limit counters are stored in each application process. A multi-instance
deployment requires a shared Redis, API gateway, or ingress rate limiter.

### 6.2 No Dedicated CSRF Protection

Flask session cookie settings reduce some risk, but state-changing requests do
not currently require dedicated CSRF tokens. This should be addressed before
an internet-facing production deployment.

### 6.3 No MFA or Durable Account Lockout

The application does not yet provide MFA, CAPTCHA, database-backed account
lockout, a production password policy, or a secure password recovery workflow.

### 6.4 No Centralized Security Audit Trail

The application does not yet emit a complete centralized audit trail for
failed logins, database access, policy denials, and administrative operations.

### 6.5 Company Database Not Yet Live-Verified

The first live company MongoDB security check has now been performed. It
identified anonymous document reads and an over-broad `readAnyDatabase` role.
See `docs/COMPANY_DB_SECURITY_ASSESSMENT.md`. Production integration remains
blocked until the database-side findings are remediated and the checker passes.

### 6.6 No SAST, DAST, or Dependency Vulnerability Report

This assessment does not yet include Semgrep or Bandit analysis, dependency CVE
scanning, OWASP ZAP, or an independent manual penetration test.

### 6.7 Local MongoDB Network Boundary

The local MongoDB instance currently binds only to `127.0.0.1` and `::1` and
requires authentication. Any future network exposure must add TLS, firewall
allowlisting, and certificate validation.

## 7. Entry Criteria for Company Database Testing

Company database verification should begin only after receiving:

- A dedicated read-only credential.
- An approved database, schema, table, and collection allowlist.
- Confirmed VPN or network allowlist requirements.
- Written confirmation that destructive tests are prohibited.
- Approved query limits and statement timeouts.
- Rate-limit requirements.
- Audit-log requirements.
- Approval from the responsible database owner.

The company environment must receive its own permission checker. The personal
MongoDB runtime-role expectations must not be assumed to match the company
database.

## 8. Evidence Files

- `tests/test_company_mongo_proxy.py`
- `tests/test_company_postgres_security.py`
- `tests/test_mongodb_permissions.py`
- `tests/test_security_and_realtime.py`
- `scripts/check_mongodb_permissions.py`
- `scripts/check_supabase_rls.py`
- `supabase/migrations/20260610000100_secure_app_tables.sql`
- `services/company_mongo_proxy.py`
- `routes/auth_routes.py`
- `routes/diagnose_routes.py`
- `routes/telemetry_routes.py`
