import csv
import os
from datetime import datetime

BENCHMARK_FILE = "benchmark_results.csv"


def log_benchmark_result(
    mode,
    prompt,
    latency_seconds,
    accuracy_score,
    tool_usage_score,
    reasoning_clarity_score,
    observability_score,
    development_complexity_score,
    integration_speed_score,
    ecosystem_score,
    maintainability_score,
    notes
):
    file_exists = os.path.exists(BENCHMARK_FILE)

    with open(BENCHMARK_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "timestamp",
                "mode",
                "prompt",
                "latency_seconds",
                "accuracy_score",
                "tool_usage_score",
                "reasoning_clarity_score",
                "observability_score",
                "development_complexity_score",
                "integration_speed_score",
                "ecosystem_score",
                "maintainability_score",
                "notes"
            ])

        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            mode,
            prompt,
            latency_seconds,
            accuracy_score,
            tool_usage_score,
            reasoning_clarity_score,
            observability_score,
            development_complexity_score,
            integration_speed_score,
            ecosystem_score,
            maintainability_score,
            notes
        ])