import json
import os
import uuid

import requests

from services.grafana_tool_registry import (
    build_grafana_workflow_policy,
    get_grafana_client_base_url,
    get_grafana_tool_by_name,
    get_kpi_rules_for_tool,
)

DEFAULT_N8N_V3_WEBHOOK_URL = "http://localhost:5678/webhook/grafana-ops-gateway"
STALE_LOCAL_TASK_BROKER_WEBHOOK_URLS = {
    "http://localhost:5679/webhook/grafana-ops-gateway",
    "http://127.0.0.1:5679/webhook/grafana-ops-gateway",
}


def get_n8n_v3_webhook_url():
    webhook_url = (
        os.getenv("N8N_V3_WEBHOOK_URL")
        or os.getenv("N8N_GRAFANA_WEBHOOK_URL")
    )

    if not webhook_url:
        return DEFAULT_N8N_V3_WEBHOOK_URL

    if webhook_url.rstrip("/") in STALE_LOCAL_TASK_BROKER_WEBHOOK_URLS:
        return DEFAULT_N8N_V3_WEBHOOK_URL

    return webhook_url


def build_n8n_v3_payload(
    *,
    user_input,
    selected_tool,
    params=None,
    source_resolution=None,
    user_id=None,
):
    tool = get_grafana_tool_by_name(selected_tool)

    if tool is None:
        raise ValueError(f"Unknown Grafana tool: {selected_tool}")

    allowed_params = set(tool.get("allowed_params") or [])
    safe_params = {
        key: value
        for key, value in (params or {}).items()
        if key in allowed_params and value is not None
    }

    return {
        "runtime": "ioa_v3_langgraph_n8n",
        "workflow_run_id": str(uuid.uuid4()),
        "source": "iot-ops-agent",
        "user_id": user_id,
        "user_input": user_input,
        "selected_source": (source_resolution or {}).get("selected_source"),
        "active_source": (source_resolution or {}).get("active_source"),
        "workflow_policy": build_grafana_workflow_policy(),
        "workflow": {
            "id": "grafana_ops_gateway",
            "tool": tool["name"],
            "workflow_id": tool["workflow_id"],
            "method": tool["method"],
            "path": tool["path"],
            "params": safe_params,
            "description": tool.get("description", ""),
        },
        "grafana_client": {
            "base_url": get_grafana_client_base_url(),
        },
        "kpi_rules": get_kpi_rules_for_tool(tool["name"]),
        "response_contract": {
            "response": "Final operational answer for the user.",
            "evidence": "Bounded Grafana API evidence.",
            "steps": [
                {
                    "thought": "Workflow step summary.",
                    "action": "n8n node or Grafana API call.",
                    "output": "Short bounded evidence.",
                }
            ],
            "policy": (
                "Use only workflow.path and workflow.params supplied by "
                "iot-ops-agent. Do not call arbitrary URLs."
            ),
        },
    }


def normalize_n8n_v3_response(data):
    if isinstance(data, list) and data:
        data = data[0]

    if not isinstance(data, dict):
        return {
            "final_answer": json.dumps(data, indent=2),
            "evidence": data,
            "steps": [],
            "token_usage": None,
        }

    final_answer = (
        data.get("response")
        or data.get("answer")
        or data.get("text")
        or data.get("output")
        or json.dumps(data, indent=2)
    )

    return {
        "final_answer": final_answer,
        "evidence": data.get("evidence") or data.get("result") or data,
        "steps": data.get("steps", []),
        "token_usage": data.get("token_usage"),
    }


def call_n8n_grafana_workflow(
    *,
    user_input,
    selected_tool,
    params=None,
    source_resolution=None,
    user_id=None,
):
    webhook_url = get_n8n_v3_webhook_url()

    if not webhook_url:
        raise RuntimeError(
            "N8N_V3_WEBHOOK_URL is not configured. "
            "Set it to the local n8n grafana_ops_gateway webhook URL."
        )

    payload = build_n8n_v3_payload(
        user_input=user_input,
        selected_tool=selected_tool,
        params=params,
        source_resolution=source_resolution,
        user_id=user_id,
    )
    response = requests.post(webhook_url, json=payload, timeout=90)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")

    if "application/json" not in content_type:
        return {
            "final_answer": response.text.strip(),
            "evidence": {"text": response.text.strip()},
            "steps": [],
            "token_usage": None,
            "request_payload": payload,
        }

    response_body = response.text.strip()

    if not response_body:
        raise RuntimeError(
            "n8n returned an empty response body for IOA v3."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "n8n returned invalid JSON for IOA v3. Raw response: "
            f"{response_body[:500]}"
        ) from exc

    result = normalize_n8n_v3_response(data)
    result["request_payload"] = payload
    return result
