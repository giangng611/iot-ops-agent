import argparse
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

from agents.ioa_v1_agent import IOAV1Agent
from agents.ioa_v2_agent import IOAV2Agent
from agents.langchain_agent import LangChainAgent
from agents.langgraph_agent import LangGraphAgent
from database import init_db
from telemetry_store import get_all_latest_devices
from simulator import DEVICES, generate_telemetry
from tools import check_system_overview, check_system_alarms
from prompts import DIAGNOSIS_OUTPUT_FORMAT


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPTS = ROOT / "eval" / "prompts_phase1.json"
DEFAULT_OUT = ROOT / "eval" / "phase1_runtime_results.csv"


MODE_LABELS = {
    "ioa_v1_custom": "IOA v1 - Custom Python",
    "ioa_v2_custom": "IOA v2 - Custom Python",
    "langchain": "IOA v2 - LangChain",
    "langgraph": "IOA v2 - LangGraph",
    "n8n_webhook": "n8n - Local Webhook",
    "dify_api": "Dify - Local API",
}


def load_prompts(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def ensure_seed_data():
    init_db()
    if len(get_all_latest_devices()) == 0:
        for device_id in DEVICES:
            generate_telemetry(device_id)


def build_local_agents(modes):
    agents = {}
    needs_openai_client = {"ioa_v1_custom", "ioa_v2_custom"}

    if needs_openai_client.intersection(modes):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for custom IOA agents.")
        client = OpenAI(api_key=api_key)

        if "ioa_v1_custom" in modes:
            agents["ioa_v1_custom"] = IOAV1Agent(client)

        if "ioa_v2_custom" in modes:
            agents["ioa_v2_custom"] = IOAV2Agent(client)

    if "langchain" in modes:
        agents["langchain"] = LangChainAgent()

    if "langgraph" in modes:
        agents["langgraph"] = LangGraphAgent()

    return agents


def run_local_agent(mode, agent, prompt):
    result = agent.run(prompt)

    if isinstance(result, dict):
        return {
            "answer": result.get("final_answer", ""),
            "steps": result.get("steps", []),
        }

    return {
        "answer": result,
        "steps": [],
    }


def run_n8n_webhook(prompt):
    webhook_url = os.getenv("EVAL_N8N_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("EVAL_N8N_WEBHOOK_URL is required for n8n_webhook mode.")

    response = requests.post(
        webhook_url,
        json={"message": prompt},
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()

    return {
        "answer": data.get("response") or data.get("text") or json.dumps(data),
        "steps": data.get("steps", []),
    }

def build_eval_operational_context():
    return {
        "latest_devices": get_all_latest_devices(),
        "system_overview": check_system_overview(),
        "system_alarms": check_system_alarms(),
    }


def build_eval_llm_prompt(prompt):
    operational_context = build_eval_operational_context()
    system_prompt = (
        "You are an IoT operations assistant. Use only the telemetry "
        "and operational context provided in this payload. Do not invent "
        "device IDs, telemetry values, alarms, or logs. Heartbeat delay "
        "values are measured in seconds. For gateway heartbeat-delay "
        "investigations, use 300 seconds as the default threshold unless "
        "the user provides a different threshold in seconds. If a user says "
        "ms or milliseconds, state that the available telemetry is stored "
        "in seconds and evaluate the stored second-based values."
    )

    return f"""
{system_prompt}

User request:
{prompt}

Required final answer format:
{DIAGNOSIS_OUTPUT_FORMAT}

Operational context JSON:
{json.dumps(operational_context, indent=2)}

Return a valid JSON object only:
{{
  "response": "final answer using the required format",
  "steps": [
    {{
      "thought": "what information you inspected",
      "action": "which Dify node, tool, or context field you used",
      "output": "short evidence from the operational context"
    }}
  ]
}}
""".strip()


def run_dify_api(prompt):
    api_url = os.getenv("EVAL_DIFY_API_URL", "http://localhost/v1/chat-messages")
    api_key = os.getenv("EVAL_DIFY_API_KEY")
    user = os.getenv("EVAL_DIFY_USER", "phase1-local-eval")

    if not api_key:
        raise RuntimeError("EVAL_DIFY_API_KEY is required for dify_api mode.")

    response = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "inputs": {
                "diagnosis_output_format": DIAGNOSIS_OUTPUT_FORMAT,
                "operational_context": json.dumps(
                    build_eval_operational_context(),
                    indent=2
                ),
            },
            "query": build_eval_llm_prompt(prompt),
            "response_mode": "blocking",
            "user": user,
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    return {
        "answer": data.get("answer") or json.dumps(data),
        "steps": data.get("metadata", {}).get("workflow_run_id", ""),
    }


def run_mode(mode, agents, prompt):
    if mode in agents:
        return run_local_agent(mode, agents[mode], prompt)

    if mode == "n8n_webhook":
        return run_n8n_webhook(prompt)

    if mode == "dify_api":
        return run_dify_api(prompt)

    raise RuntimeError(f"Unsupported mode: {mode}")


def append_result(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with open(path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(row.keys()))

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="Run Phase 1 prompts across local IoT Ops Agent runtimes."
    )
    parser.add_argument(
        "--prompts",
        default=str(DEFAULT_PROMPTS),
        help="Path to prompt set JSON.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="CSV output path.",
    )
    parser.add_argument(
        "--modes",
        default="ioa_v1_custom,ioa_v2_custom,langchain,langgraph",
        help="Comma-separated modes: ioa_v1_custom, ioa_v2_custom, langchain, langgraph, n8n_webhook, dify_api.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    ensure_seed_data()

    prompts = load_prompts(Path(args.prompts))
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    agents = build_local_agents(modes)
    output_path = Path(args.out)

    for mode in modes:
        for item in prompts:
            prompt = item["prompt"]
            started = time.time()
            status = "success"
            error = ""
            answer = ""
            steps = []

            try:
                result = run_mode(mode, agents, prompt)
                answer = result["answer"]
                steps = result["steps"]
            except Exception as exc:
                status = "error"
                error = str(exc)

            latency_seconds = round(time.time() - started, 2)
            step_count = len(steps) if isinstance(steps, list) else 1 if steps else 0

            row = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "mode": MODE_LABELS.get(mode, mode),
                "prompt_id": item["id"],
                "prompt": prompt,
                "status": status,
                "latency_seconds": latency_seconds,
                "step_count": step_count,
                "answer_preview": answer.replace("\n", " ")[:400],
                "error": error,
                "expected_focus": "; ".join(item.get("expected_focus", [])),
            }

            append_result(output_path, row)
            print(
                f"[{status}] {MODE_LABELS.get(mode, mode)} | "
                f"{item['id']} | {latency_seconds}s"
            )

    print(f"\nSaved evaluation results to: {output_path}")


if __name__ == "__main__":
    main()
