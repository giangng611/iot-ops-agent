# Benchmarking Guide

This document explains how benchmarking is performed inside IoT Ops Agent when evaluating different AI orchestration runtimes and agent architectures.

---

# Purpose

The benchmarking system is designed to compare:

* agent architectures
* orchestration runtimes
* reasoning transparency
* operational diagnosis quality
* realtime observability behavior
* engineering productivity tradeoffs

All evaluations are performed inside the same simulated IoT environment.

---

# Benchmark Philosophy

The project uses a shared operational environment:

```text
IoT telemetry
→ same database
→ same devices
→ same prompts
→ different AI runtimes
```

This allows fair comparison across multiple orchestration approaches:

* IOA v2 · Custom Python
* IOA v2 · LangChain
* IOA v2 · LangGraph
* IOA v2 · n8n
* IOA v2 · Dify

Future runtime candidates may include:

* CrewAI
* AutoGen
* local model runtimes

---

# Benchmark Data Format

Each benchmark execution is stored as one CSV row.

Example:

```text
timestamp,mode,prompt,latency_seconds,accuracy_score,tool_usage_score,reasoning_clarity_score,observability_score,development_complexity_score,integration_speed_score,ecosystem_score,maintainability_score,notes
2026-05-28T16:06:32,IOA v2 · Custom Python,/diagnose system issue,10.73,5,5,5,5,1,2,2,3,"Full reasoning trace available."
```

Each row represents one runtime, one prompt, and one execution result.


---

# Benchmark CSV Columns

| Column                       | Description                              |
| ---------------------------- | ---------------------------------------- |
| timestamp                    | Time of execution                        |
| mode                         | Agent/runtime configuration              |
| prompt                       | Operational task prompt                  |
| latency_seconds              | Total response time                      |
| accuracy_score               | Correctness of diagnosis                 |
| tool_usage_score             | Effectiveness of telemetry/tool usage    |
| reasoning_clarity_score      | Quality of operational reasoning         |
| observability_score          | Visibility into internal reasoning steps |
| development_complexity_score | Ease of implementation                   |
| integration_speed_score      | Speed of integration into the platform   |
| ecosystem_score              | Framework ecosystem maturity             |
| maintainability_score        | Long-term maintainability                |
| notes                        | Additional observations                  |

---

# Benchmark Prompt Set

The current benchmark uses five shared operational prompts.

## 1. Fleet Overview

```text
/overview system health
```

Evaluates:

* system aggregation
* telemetry summarization
* fleet-level operational awareness

---

## 2. Alert Filtering

```text
/check all unhealthy devices
```

Evaluates:

* unhealthy device detection
* telemetry interpretation
* alarm correlation
* operational prioritization

---

## 3. Root Cause Analysis

```text
/diagnose system issue
```

Evaluates:

* reasoning quality
* operational diagnosis
* remediation recommendations
* multi-step analysis capability

---

## 4. Gateway Heartbeat Investigation

```text
Investigate gateway devices with elevated heartbeat delays, identify recurring operational anomalies, and summarize the highest-risk infrastructure issues.
```

Evaluates:

* gateway-focused filtering
* heartbeat-delay interpretation
* recurring anomaly detection
* infrastructure risk prioritization

---

## 5. Sensor Alert Correlation

```text
Review all active sensor alerts and identify potential correlated failure patterns across the fleet.
```

Evaluates:

* active alert review
* cross-device correlation
* failure-pattern recognition
* fleet-level operational reasoning

---

# Scoring Rubric

Scores use a 1–5 scale.

---

## Accuracy Score

Measures whether the diagnosis is operationally correct.

| Score | Meaning                             |
| ----- | ----------------------------------- |
| 5     | Fully correct diagnosis             |
| 4     | Mostly correct with minor omissions |
| 3     | Partial diagnosis                   |
| 2     | Significant mistakes                |
| 1     | Incorrect or unusable result        |

---

## Tool Usage Score

Measures whether the runtime used telemetry and tools effectively.

| Score | Meaning                          |
| ----- | -------------------------------- |
| 5     | Correct and efficient tool usage |
| 4     | Correct but slightly redundant   |
| 3     | Partial misuse                   |
| 2     | Poor tool selection              |
| 1     | Failed tool usage                |

---

## Reasoning Clarity Score

Measures how understandable the operational reasoning is.

| Score | Meaning                    |
| ----- | -------------------------- |
| 5     | Clear multi-step reasoning |
| 4     | Mostly understandable      |
| 3     | Basic explanation          |
| 2     | Weak reasoning             |
| 1     | No meaningful reasoning    |

---

## Observability Score

Measures how visible the internal reasoning process is.

| Score | Meaning                                        |
| ----- | ---------------------------------------------- |
| 5     | Full Thought → Action → Observation visibility |
| 4     | Strong graph or framework-level traceability   |
| 3     | Partial framework trace                        |
| 2     | Minimal visibility                             |
| 1     | Black-box execution                            |

---

## Development Complexity Score

Measures implementation simplicity.

| Score | Meaning                     |
| ----- | --------------------------- |
| 5     | Very easy to implement      |
| 4     | Moderate setup              |
| 3     | Some custom logic required  |
| 2     | Complex orchestration       |
| 1     | Heavy manual implementation |

---

## Integration Speed Score

Measures how quickly the runtime can be integrated.

| Score | Meaning                      |
| ----- | ---------------------------- |
| 5     | Plug-and-play integration    |
| 4     | Minor setup required         |
| 3     | Moderate integration effort  |
| 2     | Significant engineering work |
| 1     | Difficult integration        |

---

## Ecosystem Score

Measures framework maturity and ecosystem support.

| Score | Meaning                              |
| ----- | ------------------------------------ |
| 5     | Large ecosystem and strong community |
| 4     | Strong framework support             |
| 3     | Moderate ecosystem                   |
| 2     | Limited tooling                      |
| 1     | Minimal ecosystem support            |

---

## Maintainability Score

Measures long-term maintainability.

| Score | Meaning                     |
| ----- | --------------------------- |
| 5     | Easy long-term maintenance  |
| 4     | Mostly maintainable         |
| 3     | Moderate maintenance burden |
| 2     | Difficult maintenance       |
| 1     | High maintenance overhead   |

---

# Runtime Interpretation

## IOA v2 · Custom Python

Characteristics:

* explicit ReAct-style orchestration
* realtime reasoning streaming
* full Thought → Action → Observation visibility
* custom orchestration loop
* maximum runtime control

Strengths:

* highest transparency
* strong debugging visibility
* strong telemetry grounding
* full orchestration flexibility

Tradeoffs:

* highest engineering complexity
* lower ecosystem support
* slower development workflow

Best suited for production-grade operational copilots requiring maximum transparency and orchestration control.


---

## IOA v2 · LangChain

Characteristics:

* framework-managed orchestration
* simplified tool integration
* abstraction-based agent workflow
* partial reasoning visibility

Strengths:

* rapid prototyping
* fast integration
* large ecosystem
* reduced implementation effort

Tradeoffs:

* internal orchestration becomes abstracted
* lower runtime observability
* reduced debugging transparency

Best suited for rapid AI workflow development and framework-based experimentation.

---

## IOA v2 · LangGraph

Characteristics:

* graph-based orchestration
* explicit node-based execution flow
* stronger traceability than standard LangChain
* structured state transitions
* framework-supported agent graph design

Strengths:

* strong balance between framework support and observability
* fast execution in benchmark runs
* clearer runtime structure than standard LangChain
* better traceability through graph nodes
* lower implementation burden than fully custom orchestration

Tradeoffs:

* less low-level control than custom Python
* more implementation effort than standard LangChain
* graph structure must be designed carefully

Best suited for stateful operational agents requiring a balance of framework support,
runtime structure, and reasoning transparency.

---

## IOA v2 · n8n

Characteristics:

* local external workflow runtime
* webhook-based integration from the IoT Ops Agent UI
* OpenAI Chat Model execution inside the n8n workflow
* JSON response contract back to Flask
* UI-visible Thought → Action → Observation trace
* n8n execution history for workflow-level debugging

Strengths:

* fastest visual workflow integration path
* strong workflow observability through n8n executions
* easy to extend toward Slack, HTTP APIs, MQTT, notification channels, and automation workflows
* separates orchestration workflow design from Flask application code

Tradeoffs:

* telemetry/tool execution is indirect because Flask packages operational context before sending it to n8n
* response formatting depends on the n8n workflow contract
* less low-level reasoning-loop control than Custom Python or LangGraph

Best suited for workflow automation, external integrations, and low-code orchestration around the IoT Ops Agent backend.

---

## IOA v2 · Dify

Characteristics:

* self-hosted Dify Chatflow runtime
* Chat Messages API integration from the IoT Ops Agent UI
* backend-packaged operational context passed into Dify app inputs and prompt text
* Dify app API key configured through `.env`
* UI-visible reasoning trace normalized back into Flask SSE events
* local Dify execution through Docker/Colima or Docker Desktop

Strengths:

* strong chatbot-native workflow for operational diagnosis
* high integration speed after Dify is running locally
* less workflow configuration overhead than n8n for text-based chatbot diagnosis
* good operational answer quality and structured evidence
* reasoning traces usually contain 3-5 visible investigation steps in local testing

Tradeoffs:

* lower low-level tool-loop control than Custom Python or LangGraph
* telemetry/tool execution is indirect because Flask packages context before sending it to Dify
* requires a published Dify app and app API key
* model/provider cost depends on the LLM configured inside Dify

Best suited for chatbot-native agent testing and fast app-level experimentation with self-hosted framework infrastructure.

---

# Runtime Benchmark Results

The benchmark tested shared prompts across five orchestration runtimes. Dify was added after the initial Custom Python, LangChain, LangGraph, and n8n comparison and was evaluated through the same IoT Ops Agent UI.

| Runtime                | Avg Accuracy | Avg Tool Usage | Avg Reasoning Clarity | Avg Observability | Avg Latency | Dev Complexity | Integration Speed | Ecosystem | Maintainability |
| ---------------------- | -----------: | -------------: | --------------------: | ----------------: | ----------: | -------------: | ----------------: | --------: | --------------: |
| IOA v2 · Custom Python |          5.0 |            5.0 |                   5.0 |               5.0 |      16.50s |            1.0 |               2.0 |       2.0 |             3.0 |
| IOA v2 · LangChain     |          3.0 |            3.0 |                   4.0 |               2.0 |      12.85s |            5.0 |               5.0 |       5.0 |             4.0 |
| IOA v2 · LangGraph     |          5.0 |            5.0 |                   5.0 |               4.0 |       9.50s |            4.0 |               4.0 |       4.0 |             4.0 |
| IOA v2 · n8n           |          4.2 |            4.0 |                   4.2 |               4.0 |       8.53s |            4.0 |               5.0 |       4.0 |             4.0 |
| IOA v2 · Dify          |          4.0 |           4.17 |                   4.0 |              3.83 |       8.06s |            4.0 |               5.0 |       4.0 |             4.0 |

---

# Detailed Benchmark Rows

Rows are grouped by prompt. Runtime order is Custom Python, LangChain, LangGraph, n8n, then Dify where Dify results are available.

| Prompt | Runtime | Latency | Accuracy | Tool Usage | Reasoning | Observability | Notes |
| ------ | ------- | ------: | -------: | ---------: | --------: | ------------: | ----- |
| `/diagnose system issue` | IOA v2 · Custom Python | 10.73s | 5 | 5 | 5 | 5 | Correctly identified warning-level fleet issue, cited affected devices, alarm types, metrics, likely causes, and concrete next actions. |
| `/diagnose system issue` | IOA v2 · LangChain | 8.31s | 3 | 3 | 4 | 2 | Faster response and clear structure, but affected device list appears inconsistent with the previous telemetry snapshot and reasoning/tool trace visibility is limited. |
| `/diagnose system issue` | IOA v2 · LangGraph | 8.24s | 5 | 5 | 5 | 4 | Strong root-cause analysis focused on overloaded gateways, resource exhaustion, and operational remediation. |
| `/diagnose system issue` | IOA v2 · n8n | 10.76s | 5 | 4 | 5 | 4 | Used latest devices, system alarms, and system overview; returned four Thought-Action-Observation iterations and the required diagnosis format. |
| `/diagnose system issue` | IOA v2 · Dify | 5.79s | 4 | 4 | 4 | 3 | Diagnosed the main system issues with concise evidence and next actions. Trace was shorter at three steps and less tool-explicit than Custom Python or LangGraph. |
| `/overview system health` | IOA v2 · Custom Python | 9.97s | 5 | 5 | 5 | 5 | Accurate fleet summary with healthy/warning/critical counts, affected devices, alarm evidence, likely causes, and next actions. |
| `/overview system health` | IOA v2 · LangChain | 12.45s | 3 | 3 | 4 | 2 | Clear structure, but device status/details appear inconsistent with the previous telemetry snapshot. |
| `/overview system health` | IOA v2 · LangGraph | 5.79s | 5 | 5 | 5 | 4 | Accurate device grouping, detailed evidence, likely causes, and remediation steps. |
| `/overview system health` | IOA v2 · n8n | 10.14s | 4 | 4 | 4 | 4 | Generated a system health overview from backend operational context with fleet counts, unhealthy devices, active alarms, likely causes, and next actions. |
| `/overview system health` | IOA v2 · Dify | 9.09s | 4 | 4 | 4 | 4 | Produced a grounded fleet overview with health counts, affected gateways and sensors, active alarms, and a four-step UI-visible reasoning trace. |
| `/check all unhealthy devices` | IOA v2 · Custom Python | 9.41s | 5 | 5 | 5 | 5 | Correctly identified unhealthy devices, separated critical and warning states, cited telemetry evidence, and provided remediation steps. |
| `/check all unhealthy devices` | IOA v2 · LangChain | 13.09s | 3 | 3 | 4 | 2 | Clear operational format, but device statuses and telemetry details appear inconsistent with the previous custom runtime snapshot. |
| `/check all unhealthy devices` | IOA v2 · LangGraph | 5.96s | 5 | 5 | 5 | 4 | Accurately identified unhealthy devices, separated critical and warning conditions, cited telemetry metrics, and provided operational guidance. |
| `/check all unhealthy devices` | IOA v2 · n8n | 7.83s | 4 | 4 | 4 | 4 | Identified unhealthy devices from operational context and returned structured diagnosis with evidence, likely cause, and remediation actions. |
| `/check all unhealthy devices` | IOA v2 · Dify | 5.71s | 4 | 4 | 4 | 4 | Identified unhealthy devices, cited heartbeat, CPU, memory, and alarm evidence, and returned a four-step trace with remediation guidance. |
| Gateway heartbeat investigation | IOA v2 · Custom Python | 35.12s | 5 | 5 | 5 | 5 | Most explicit tool-driven reasoning and observability for complex gateway investigation, but highest latency and implementation complexity. |
| Gateway heartbeat investigation | IOA v2 · LangChain | 15.15s | 3 | 3 | 4 | 2 | Faster response with usable structure, but operational evidence is less auditable than Custom Python or LangGraph. |
| Gateway heartbeat investigation | IOA v2 · LangGraph | 14.04s | 5 | 5 | 5 | 4 | Strong structured orchestration for multi-step gateway analysis, with better traceability than LangChain and lower latency than Custom Python. |
| Gateway heartbeat investigation | IOA v2 · n8n | 7.39s | 4 | 4 | 4 | 4 | Identified gateway heartbeat-delay issues and correlated them with CPU, memory, and alarm context. |
| Gateway heartbeat investigation | IOA v2 · Dify | 10.27s | 5 | 5 | 4 | 4 | Correctly identified the gateway crossing the configured heartbeat threshold, distinguished lower-risk devices, and produced a five-step trace. |
| Active sensor alert correlation | IOA v2 · Custom Python | 17.25s | 5 | 5 | 5 | 5 | Strongest for detailed alert correlation because it exposes the full reasoning/tool loop and cites operational evidence step by step. |
| Active sensor alert correlation | IOA v2 · LangChain | 15.25s | 3 | 3 | 4 | 2 | Usable structured response, but traceability is limited and correlation evidence is less transparent. |
| Active sensor alert correlation | IOA v2 · LangGraph | 13.49s | 5 | 5 | 5 | 4 | Effective for correlated alert analysis because graph node execution improves reasoning structure, auditability, and workflow control. |
| Active sensor alert correlation | IOA v2 · n8n | 6.55s | 4 | 4 | 4 | 4 | Reviewed active alarm context, identified correlated CPU, memory, and heartbeat-delay patterns, and returned structured recommendations. |
| Active sensor alert correlation | IOA v2 · Dify | 8.98s | 4 | 4 | 4 | 4 | Reviewed active sensor and gateway alarms, identified correlated heartbeat-delay and high-CPU patterns, and returned a five-step trace. |

---

# Key Benchmark Findings

The benchmark demonstrates a clear engineering tradeoff between runtime transparency and orchestration control versus framework abstraction and development speed.

## Custom Python

The custom IOA v2 runtime achieved the strongest observability because the orchestration loop was explicitly implemented and streamed step-by-step.

It is the best fit when:

* full reasoning visibility is required
* debugging control matters
* custom orchestration behavior is important

---

## LangChain

LangChain provided the fastest framework-level integration path, but its internal orchestration behavior was more abstracted.

It is the best fit when:

* rapid prototyping is the priority
* ecosystem integrations matter
* lower implementation effort is preferred

---

## LangGraph

LangGraph offered the strongest balance among code-native frameworks.

It preserved much of the framework productivity advantage while improving traceability through graph-based node execution.

It is the best fit when:

* stateful orchestration is needed
* framework support is useful
* reasoning traceability still matters
* graph-based workflow design fits the application

---

## n8n

n8n was successfully installed and evaluated locally as an external workflow runtime.

It receives the same operational prompts through the IoT Ops Agent UI, calls an OpenAI Chat Model inside the n8n workflow, formats the result with a Code node, and returns JSON through `Respond to Webhook`.

It is the best fit when:

* low-code workflow orchestration is important
* external integrations such as Slack, HTTP APIs, MQTT, or notification channels are needed
* visual execution logs are useful for debugging
* fast integration speed matters more than low-level reasoning-loop control

In local benchmark runs, n8n had the fastest average latency among the evaluated runtimes and the highest integration speed score. Its main limitation is that telemetry and tool execution are indirect: the Flask backend packages the operational context before sending it to the workflow.

---

## Dify

Dify was successfully installed locally as a self-hosted Chatflow runtime and integrated into the IoT Ops Agent UI/backend.

It receives the same backend-packaged operational context as n8n, but requires less workflow construction for chatbot-style answers. The Dify app is called through `/v1/chat-messages` using an app API key.

It is the best fit when:

* chatbot-native behavior is the priority
* fast app-level iteration is preferred
* less manual workflow configuration is desired compared with n8n
* a self-hosted framework with model/provider configuration is useful

In local benchmark runs, Dify returned thoughtful structured answers with at least three reasoning iterations per run and an average latency of about 8 seconds. Its main limitation is that trace steps are model-generated/app-level reasoning rather than direct low-level tool execution traces.

---

# Important Notes

The benchmark system is intentionally semi-subjective.

Scores such as:

* accuracy
* reasoning clarity
* observability

are assigned using human evaluation based on operational outputs and runtime behavior.

The goal is not perfect scientific scoring. The goal is engineering evaluation of AI orchestration tradeoffs.

---

# Long-Term Goal

The benchmarking layer allows IoT Ops Agent to evolve into
an AI orchestration evaluation platform where multiple runtimes and agent architectures can be tested against the same operational environment.
