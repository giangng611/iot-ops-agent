import argparse
import csv
import json
import os
import statistics
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "eval" / "phase1_runtime_results.csv"
DEFAULT_OUTPUT = ROOT / "eval" / "phase1_judged_results.csv"
QUALITY_FIELDS = (
    "factual_correctness",
    "evidence_grounding",
    "task_completion",
    "actionability",
    "source_discipline",
)


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def append_row(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with open(path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(row.keys()))

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def has_tool_evidence(row):
    try:
        steps = json.loads(row.get("steps_json") or "[]")
    except json.JSONDecodeError:
        return False

    if not isinstance(steps, list):
        return bool(steps)

    return any(
        isinstance(step, dict)
        and step.get("action")
        and step.get("output") not in (None, "", {}, [])
        for step in steps
    )


def build_judge_prompt(row):
    return f"""
You are an independent evaluator of an IoT operations assistant.
The runtime identity is intentionally hidden. Judge only the answer against
the user task and the reference operational context.

User task:
{row.get("prompt", "")}

Expected task focus:
{row.get("expected_focus", "")}

Reference operational context:
{row.get("reference_context_json", "")}

Assistant answer:
{row.get("answer", "")}

Score each quality dimension from 1 to 5:
- factual_correctness: claims match the reference context.
- evidence_grounding: important claims cite concrete available evidence.
- task_completion: the answer satisfies the requested operational task.
- actionability: next actions are specific, safe, and useful.
- source_discipline: no invented devices, metrics, alarms, or unsupported
  company-rule semantics.

Do not score latency, token usage, trace visibility, framework popularity,
implementation complexity, or ecosystem maturity. Those are measured
separately.

Return one JSON object only:
{{
  "factual_correctness": 1,
  "evidence_grounding": 1,
  "task_completion": 1,
  "actionability": 1,
  "source_discipline": 1,
  "critical_error": false,
  "rationale": "Short evidence-based explanation."
}}
""".strip()


def judge_once(client, model, row):
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Apply the rubric consistently. Penalize unsupported "
                    "claims even when the prose sounds convincing."
                ),
            },
            {"role": "user", "content": build_judge_prompt(row)},
        ],
    )
    result = json.loads(response.choices[0].message.content)

    for field in QUALITY_FIELDS:
        score = int(result[field])
        result[field] = max(1, min(score, 5))

    critical_error = result.get("critical_error", False)
    if isinstance(critical_error, str):
        critical_error = critical_error.strip().lower() == "true"
    result["critical_error"] = bool(critical_error)
    result["rationale"] = str(result.get("rationale") or "").strip()
    return result


def aggregate_judgments(judgments):
    aggregated = {
        field: statistics.median(
            judgment[field] for judgment in judgments
        )
        for field in QUALITY_FIELDS
    }
    aggregated["quality_score"] = round(
        sum(aggregated.values()) / len(QUALITY_FIELDS),
        2,
    )
    aggregated["critical_error"] = any(
        judgment["critical_error"] for judgment in judgments
    )
    aggregated["judge_rationales"] = json.dumps(
        [judgment["rationale"] for judgment in judgments],
        ensure_ascii=False,
    )
    return aggregated


def main():
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Blind AI-as-judge scoring for runtime benchmark results."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--model",
        default=os.getenv("BENCHMARK_JUDGE_MODEL", "gpt-4.1-mini"),
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Use 3 or more repetitions and median scores for formal runs.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to an existing output instead of replacing it.",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for AI judging.")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    repetitions = max(1, args.repetitions)
    output_path = Path(args.output)
    if output_path.exists() and not args.append:
        output_path.unlink()

    for row in load_rows(Path(args.input)):
        if row.get("status") != "success" or not row.get("answer"):
            continue

        judgments = [
            judge_once(client, args.model, row)
            for _ in range(repetitions)
        ]
        judged_row = {
            **row,
            **aggregate_judgments(judgments),
            "judge_model": args.model,
            "judge_repetitions": repetitions,
            "has_tool_evidence": has_tool_evidence(row),
        }
        append_row(output_path, judged_row)
        print(
            f"[judged] {row.get('prompt_id')} | "
            f"{row.get('mode')} | "
            f"quality={judged_row['quality_score']}"
        )

    print(f"\nSaved judged results to: {output_path}")


if __name__ == "__main__":
    main()
