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

This allows fair comparison across:

* IOA v1 · Custom Python
* IOA v2 · Custom Python
* IOA v2 · LangChain

Future evaluation phases may include:

* LangGraph
* Dify
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

Each row represents:

```text
one runtime
+ one prompt
+ one execution result
```

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
| 4     | Strong traceability                            |
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
* full observability
* custom orchestration loop
* maximum runtime control

Strengths:

* transparency
* debugging visibility
* telemetry grounding
* orchestration flexibility

Tradeoffs:

* higher engineering complexity
* lower ecosystem support
* slower development workflow

Best suited for:

```text
production-grade operational copilots
requiring maximum transparency and orchestration control
```

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

Best suited for:

```text
rapid AI workflow development
and framework-based experimentation
```

---

# Benchmark Aggregation

Raw CSV rows represent individual executions.

Final evaluation tables aggregate averages across multiple runs.

Example:

| Runtime                | Avg Accuracy | Avg Observability | Avg Latency | Dev Complexity | Integration Speed |
| ---------------------- | ------------ | ----------------- | ----------- | -------------- | ----------------- |
| IOA v2 · Custom Python | 5.0          | 5.0               | 10.04s      | 1.0            | 2.0               |
| IOA v2 · LangChain     | 3.0          | 2.0               | 11.28s      | 5.0            | 5.0               |

---

# Key Benchmark Finding

The benchmark demonstrates a clear engineering tradeoff between:

```text
runtime transparency and orchestration control
vs
framework abstraction and development speed
```

The custom IOA v2 runtime achieved stronger:

* reasoning visibility
* telemetry grounding
* operational traceability
* debugging transparency

because the orchestration loop was explicitly implemented and streamed step-by-step.

LangChain reduced implementation complexity and accelerated integration, but internal reasoning behavior became more abstracted due to framework-managed orchestration.

---

# Important Notes

The benchmark system is intentionally semi-subjective.

Scores such as:

* accuracy
* reasoning clarity
* observability

are assigned using human evaluation based on operational outputs and runtime behavior.

The goal is not perfect scientific scoring. The goal is engineering evaluation of AI orchestration tradeoffs
