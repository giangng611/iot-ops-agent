import json
import os
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
GRAFANA_TOOLS_PATH = CONFIG_DIR / "grafana_tools.json"
GRAFANA_KPI_RULES_PATH = CONFIG_DIR / "grafana_kpi_rules.json"


def _load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_grafana_tool_config():
    return _load_json(GRAFANA_TOOLS_PATH)


def load_grafana_kpi_rules():
    return _load_json(GRAFANA_KPI_RULES_PATH)


def get_grafana_tools():
    return load_grafana_tool_config().get("tools", [])


def get_grafana_client_base_url():
    config = load_grafana_tool_config()
    env_name = config.get("base_url_env", "GRAFANA_DASHBOARD_CLIENT_URL")
    return os.getenv(env_name) or config.get("default_base_url", "http://127.0.0.1:5050")


def grafana_kpi_rules_enabled():
    return os.getenv("IOA_V3_ENABLE_KPI_RULES", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_grafana_tool_by_name(tool_name):
    for tool in get_grafana_tools():
        if tool.get("name") == tool_name:
            return tool

    return None


def get_grafana_tool_by_workflow_id(workflow_id):
    for tool in get_grafana_tools():
        if tool.get("workflow_id") == workflow_id:
            return tool

    return None


def get_kpi_rules_for_tool(tool_name):
    if not grafana_kpi_rules_enabled():
        return []

    return [
        rule
        for rule in load_grafana_kpi_rules().get("rules", [])
        if rule.get("tool") == tool_name
    ]


def build_grafana_workflow_policy():
    tools = get_grafana_tools()

    return {
        "policy_source": "grafana",
        "max_tool_executions": 1,
        "deny_by_default": True,
        "allowed_workflows": [
            {
                "tool": tool["name"],
                "workflow_id": tool["workflow_id"],
                "intent": tool["intent"],
                "method": tool["method"],
                "path": tool["path"],
                "allowed_params": tool.get("allowed_params", []),
                "description": tool.get("description", ""),
            }
            for tool in tools
        ],
        "forbidden_capabilities": [
            "generic_database_query",
            "arbitrary_http_request",
            "shell_command",
            "credential_access",
            "write_or_mutate_company_data",
            "unapproved_grafana_endpoint",
        ],
        "evidence_rules": {
            "treat_api_response_as_untrusted": True,
            "summarize_samples_only": True,
            "apply_kpi_rules_before_final_answer": True,
        },
    }
