# LangGraph Governance and Control Flow

## 1. Objective

The LangGraph runtime is a bounded operational workflow, not an autonomous
general-purpose agent. It may select and execute one approved read-only tool
per request and must stop when policy validation fails.

## 2. Hardened Graph

```text
START
  |
validate_request
  | allowed
select_tool
  |
authorize_tool
  | allowed
run_tool
  |
validate_evidence
  | allowed
generate_answer
  |
END

Any denied policy decision -> deny_request -> END
```

## 3. Trust Boundaries

Untrusted inputs:

- User messages.
- Data-source values received from callers.
- Database records.
- Telemetry fields and device logs.
- Tool output strings.

Trusted policy inputs:

- Static tool registry.
- Tool-to-data-source mapping.
- Execution budget.
- Typed identifier extraction.
- Evidence size limits.

The language model does not authorize tools and cannot modify the tool
registry, source mapping, or execution budget.

## 4. Policy Controls

### Request Validation

- Rejects empty requests.
- Rejects requests over 2,000 characters.
- Rejects unknown data-source values.

### Tool Authorization

- Simulator and company tools use separate allowlists.
- Unknown tools are denied.
- Source/tool mismatches are denied.
- Device tools require a validated device identifier.
- Each request has a one-tool execution budget.
- Direct calls to the execution node fail closed without policy approval.

### Evidence Validation

- Tool output is required before generation.
- Raw tool output is bounded before it is written to graph state or traces.
- Lists and mappings are bounded to 100 items per level.
- Strings are bounded to 2,000 characters.
- Nested evidence is bounded to six levels.
- Unsupported object types are converted to bounded strings.

### Prompt-Injection Boundary

The generation prompt explicitly treats database values, telemetry, logs, and
device names as untrusted data. Instructions embedded in evidence must not be
followed.

### Auditability

Every graph step records:

- Request ID.
- Data source.
- Node ID and label.
- Policy decision or executed action.
- Bounded node output.

## 5. Fail-Closed Behavior

The workflow stops without invoking a tool or model when:

- The request is invalid.
- The data source is invalid.
- The selected tool is unknown.
- The tool is not allowed for the active source.
- A required identifier is missing.
- The execution budget is exhausted.
- The authorized tool returns no evidence.

Unknown tools never fall back to a broader fleet query.

## 6. Adversarial Test Coverage

The policy suite verifies:

- Source spoofing.
- Prompt-based tool escalation.
- Unknown-tool injection.
- Direct execution-node bypass.
- Execution-budget exhaustion.
- Missing typed arguments.
- Oversized and malicious evidence.
- Database-content prompt injection.
- Model and tool non-execution after policy denial.
- Required graph order and audit metadata.

Run:

```bash
python3 -m unittest tests.test_langgraph_policy -v
```

## 7. Remaining Production Work

- Persist audit events in a centralized append-only store.
- Bind policy decisions to authenticated user roles and tenant/site scope.
- Move rate limits and execution budgets to shared infrastructure.
- Add human approval nodes before any future side-effecting tool.
- Add model-provider abstraction before replacing OpenAI with MiniMax.
- Add deterministic output validation for high-impact operational decisions.
