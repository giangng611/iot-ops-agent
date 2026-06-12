# Benchmarking Guide

The benchmark compares agent runtimes on the same operational tasks without
treating manually assigned scores as measured evidence.

## Evaluation Boundary

The current candidates are:

* IOA v1 · Custom Python
* IOA v2 · Custom Python
* IOA v2 · LangChain
* IOA v2 · LangGraph
* IOA v2 · n8n
* IOA v2 · Dify

Answer quality and engineering tradeoffs are evaluated separately.

## 1. Freeze Tasks and Evidence

The prompt set is stored in `eval/prompts_phase1.json`. For each execution,
the runner captures:

* runtime and prompt ID
* success or error status
* end-to-end latency
* full answer
* reasoning/tool steps
* token usage when exposed by the runtime
* the operational reference context used for evaluation

Run the local candidates:

```bash
python -m scripts.evaluate_local_runtimes
```

Select runtimes explicitly when external services are available:

```bash
python -m scripts.evaluate_local_runtimes \
  --modes ioa_v2_custom,langchain,langgraph,n8n_webhook,dify_api
```

Formal comparisons should pause telemetry writes or restore the same database
snapshot before each runtime. Capturing context before each run is useful for
audit, but it does not make changing telemetry identical.

## 2. Measure Objective Signals

The runner records values that do not require an LLM judgment:

* execution success
* latency
* trace step count
* token usage when available

The judge output also derives `has_tool_evidence` from structured steps.

Do not infer missing token counts or assign a quality score merely because a
request succeeded. `benchmark_results.csv` is a live execution log; zero
quality fields mean “not judged,” not a score of zero.

## 3. Blind AI-as-Judge

The judge receives the task, expected focus, frozen reference context, and
answer. It does not receive the runtime label.

```bash
python -m scripts.judge_runtime_results --repetitions 3
```

The output defaults to `eval/phase1_judged_results.csv`. The judge scores each
answer from 1 to 5 on:

* factual correctness
* evidence grounding
* task completion
* actionability
* source discipline

It also records a critical-error flag and evidence-based rationale.

For a decision-quality run:

* keep the judge model and prompt fixed
* use at least three repetitions and median aggregation
* randomize runtime order
* calibrate a sample with human review
* report critical errors separately from averages
* retain raw answers and reference context for audit

## 4. Engineering Evaluation

Implementation effort, maintainability, ecosystem maturity, deployment
constraints, and observability are architecture criteria, not answer-quality
scores. Record them in a separate decision table with concrete evidence such
as:

* code and configuration surface
* external services required
* failure and fallback behavior
* trace fidelity
* operational ownership
* security boundary

## Company Agent Tasks

The benchmark should increasingly reflect the target company problem rather
than generic chatbot quality. Recommended task groups are:

* fleet and inventory summary
* disconnected-device investigation
* telemetry coverage and unmapped-record analysis
* one-device diagnosis
* provisional alert explanation
* official-rule readiness and Grafana handoff
* numeric threshold evidence scans
* explicit Company DB disconnection and simulator fallback

See [Company Operational Agent Scope](COMPANY_AGENT_SCOPE.md).

## Interpretation

No runtime is declared the winner in the repository documentation. A runtime
should be selected only after a fresh, reproducible run against the intended
company tasks and deployment constraints.

Historical manually scored tables were removed from the current guide because
they were PoC observations rather than repeatable selection evidence.
