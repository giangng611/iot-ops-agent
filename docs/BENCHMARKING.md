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

Future evaluation phases may include:

* Dify
* n8n
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

Phase 1 uses three shared operational prompts.

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
* faster execution in Phase 1 benchmark runs
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

# Phase 1 Benchmark Results

The Phase 1 benchmark tested three shared prompts across three orchestration runtimes.

| Runtime                | Avg Accuracy | Avg Tool Usage | Avg Reasoning Clarity | Avg Observability | Avg Latency | Dev Complexity | Integration Speed | Ecosystem | Maintainability |
| ---------------------- | -----------: | -------------: | --------------------: | ----------------: | ----------: | -------------: | ----------------: | --------: | --------------: |
| IOA v2 · Custom Python |          5.0 |            5.0 |                   5.0 |               5.0 |      10.04s |            1.0 |               2.0 |       2.0 |             3.0 |
| IOA v2 · LangChain     |          3.0 |            3.0 |                   4.0 |               2.0 |      11.28s |            5.0 |               5.0 |       5.0 |             4.0 |
| IOA v2 · LangGraph     |          5.0 |            5.0 |                   5.0 |               4.0 |       6.66s |            4.0 |               4.0 |       4.0 |             4.0 |

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

LangGraph offered the strongest balance in Phase 1.

It preserved much of the framework productivity advantage while improving traceability through graph-based node execution.

It is the best fit when:

* stateful orchestration is needed
* framework support is useful
* reasoning traceability still matters
* graph-based workflow design fits the application

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
