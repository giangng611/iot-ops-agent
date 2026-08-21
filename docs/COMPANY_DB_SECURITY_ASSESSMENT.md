# Company MongoDB Security Assessment

Assessment date: June 15, 2026

## 1. Executive Result

Status: **FAIL - blocked for production or sensitive-data use**

The application can connect to the company MongoDB server, but the current
database-side controls do not satisfy the required security baseline.

Two material findings were confirmed:

1. Anonymous clients can execute document reads against an operational
   collection.
2. The application credential has the `readAnyDatabase` role and can read every
   database on the MongoDB server.

No destructive operation was executed during this assessment.

## 2. Environment Under Test

Database type:

```text
MongoDB
```

Network endpoint:

```text
<internal-company-mongodb-host>:27017
```

Authenticated identity:

```text
<redacted-read-account>@admin
```

Assigned role:

```text
readAnyDatabase@admin
```

Application-approved namespaces:

```text
authorization.IDENTITY
datamgmt.CIN
datamgmt.CNT
datamgmt.DEVICE_TELEMETRY
datamgmt.RULE
devicemgmt.NODE
orchestration.URI_MAPPER
subNNotif.AE
subNNotif.SUB
```

Credentials and document values are intentionally excluded from this report.

## 3. Finding CDB-001: Anonymous Document Reads

Severity: **Critical**

### Evidence

The checker connected to the server without a username or password and issued
a bounded `find_one` request against an approved operational namespace.

Observed result:

```text
anonymous_document_access_denied=false
```

No document value was printed or retained. The test recorded only whether the
server denied or accepted the operation.

### Risk

Any host with network access to this MongoDB endpoint may be able to read
operational data without possessing a database credential.

Application authentication, Flask sessions, and the company MongoDB proxy do
not protect direct connections to the database server.

### Required Remediation

The database owner should:

1. Enable MongoDB authorization.
2. Confirm that unauthenticated `find`, collection discovery, and database
   discovery operations return `Unauthorized`.
3. Restrict port `27017` through a firewall, security group, or network ACL.
4. Allow access only from approved application hosts or subnets.
5. Require TLS if traffic crosses an untrusted or shared network.
6. Rotate credentials after authorization is enabled.

Example MongoDB configuration:

```yaml
security:
  authorization: enabled
```

The exact deployment procedure must be owned and approved by the company
database administrator.

## 4. Finding CDB-002: Excessive Read Scope

Severity: **High**

### Evidence

The authenticated connection reported:

```text
role=readAnyDatabase
resource.db=""
resource.collection=""
```

The empty database and collection resource means the read privilege applies
across the server rather than only to the application-approved data sources.

Observed checker result:

```text
least_privilege=false
```

### Risk

If the application credential is disclosed or misused, the actor can read data
from unrelated databases hosted on the same MongoDB server.

### Required Remediation

Replace `readAnyDatabase` with a dedicated application role restricted to:

```text
authorization
datamgmt
devicemgmt
```

Prefer collection-level privileges for:

```text
authorization.IDENTITY
datamgmt.CIN
datamgmt.CNT
datamgmt.DEVICE_TELEMETRY
datamgmt.RULE
devicemgmt.NODE
```

The application account must not receive:

- `readWrite`
- `dbAdmin`
- `userAdmin`
- `clusterAdmin`
- `root`
- `insert`
- `update`
- `remove`
- collection or database drop privileges

## 5. Positive Controls Confirmed

The credential metadata did not include document write actions such as:

- `insert`
- `update`
- `remove`

The application proxy now additionally enforces:

- An exact database and collection namespace allowlist.
- Identifier validation.
- Dangerous MongoDB operator blocking.
- Query result limits.
- Server-side query timeouts.
- Process-local operation rate limits.
- Read-only methods only.

These application controls reduce accidental or LLM-originated access, but
they do not remediate direct anonymous database access.

## 6. Application-Side Mitigation Added

The proxy now defaults to the following allowlist:

```text
authorization.IDENTITY
datamgmt.CIN
datamgmt.CNT
datamgmt.DEVICE_TELEMETRY
datamgmt.RULE
devicemgmt.NODE
```

It can be configured through:

```env
COMPANY_MONGO_ALLOWED_NAMESPACES=devicemgmt.NODE,authorization.IDENTITY,datamgmt.CNT,datamgmt.CIN,datamgmt.DEVICE_TELEMETRY,datamgmt.RULE,subNNotif.AE,subNNotif.SUB,orchestration.URI_MAPPER
```

Database and collection discovery results are filtered through the same
allowlist. A syntactically valid namespace is not sufficient to gain access.

## 7. Verification Method

Automated checker:

```bash
python3 scripts/check_company_mongodb_security.py
```

The checker performs only:

- Authenticated `connectionStatus` privilege inspection.
- Comparison against the approved namespace allowlist.
- Detection of write and administrative actions.
- A bounded anonymous document-read denial check.

The checker does not:

- Insert data.
- Update data.
- Delete data.
- Create or remove indexes.
- Print document values.
- Run a load or stress test.

## 8. Acceptance Criteria for Retest

The company MongoDB security check may pass only when:

- `anonymous_document_access_denied=true`
- `least_privilege=true`
- The account is authenticated.
- No write or administrative action is granted.
- No privilege applies to every database.
- Every privilege is limited to an approved database or namespace.

After remediation, rerun:

```bash
python3 scripts/check_company_mongodb_security.py
python3 -m unittest discover -s tests -v
```

## 9. Decision

Do not treat the current company MongoDB connection as production-secure.

The proof of concept may continue only with non-sensitive demonstration data
and explicit acknowledgement of these findings. Production or sensitive-data
integration should remain blocked until both findings are remediated and the
checker passes.
