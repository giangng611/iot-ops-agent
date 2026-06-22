from storage.relational_store import (
    create_prompt,
    delete_prompt,
    get_prompts,
    update_prompt,
)


DEFAULT_PROMPTS = [
    {
        "id": "default-1",
        "title": "Core KPI Overview",
        "command": "Review core IoT platform KPIs: availability, connected devices rate, ingestion health, API success, and any data quality gaps.",
        "category": "KPI Core",
        "is_default": 1,
    },
    {
        "id": "default-2",
        "title": "Connectivity Coverage",
        "command": "Check company device connectivity coverage, disconnected devices, and telemetry coverage gaps.",
        "category": "KPI Core",
        "is_default": 1,
    },
    {
        "id": "default-3",
        "title": "Ingestion Queue Health",
        "command": "Check RabbitMQ queue backlog and throughput, then explain whether ingestion pressure may affect telemetry freshness.",
        "category": "Ingestion",
        "is_default": 1,
    },
    {
        "id": "default-4",
        "title": "API Health KPI",
        "command": "Check HTTP API success, 5xx errors, and p95 latency against the platform KPI guidance.",
        "category": "API & Application",
        "is_default": 1,
    },
    {
        "id": "default-5",
        "title": "Infrastructure Drilldown",
        "command": "Check Kubernetes, Linux node, Redis, MongoDB, and MySQL health as diagnostic evidence for platform issues.",
        "category": "Diagnostics",
        "is_default": 1,
    },
    {
        "id": "default-6",
        "title": "Alert Readiness",
        "command": "Review company rule readiness, provisional alert evidence, and the remaining Grafana integration gaps.",
        "category": "Alerts",
        "is_default": 1,
    },
    {
        "id": "default-7",
        "title": "Manual Threshold Scan",
        "command": "Scan company telemetry payloads for measured values above a specified threshold, then state that this is not an official alert rule.",
        "category": "Data Quality",
        "is_default": 1,
    },
    {
        "id": "company-1",
        "title": "Company Fleet Snapshot",
        "command": "/company fleet snapshot",
        "category": "Company PoC",
        "is_default": 1,
    },
    {
        "id": "company-2",
        "title": "Company Device Inventory",
        "command": "/company inventory and node overview",
        "category": "Company PoC",
        "is_default": 1,
    },
    {
        "id": "company-3",
        "title": "Telemetry Coverage",
        "command": "/company telemetry coverage and unmapped records",
        "category": "Company PoC",
        "is_default": 1,
    },
    {
        "id": "company-4",
        "title": "Provisional PoC Alerts",
        "command": "/company provisional alerts with evidence",
        "category": "Company PoC",
        "is_default": 1,
    },
    {
        "id": "company-5",
        "title": "Disconnected Company Devices",
        "command": "/company disconnected devices",
        "category": "Company PoC",
        "is_default": 1,
    },
    {
        "id": "company-6",
        "title": "High Temperature Findings",
        "command": "/company temperature alerts and measured values",
        "category": "Company PoC",
        "is_default": 1,
    },
    {
        "id": "company-7",
        "title": "Rule Integration Readiness",
        "command": "/company rule readiness and Grafana gaps",
        "category": "Company PoC",
        "is_default": 1,
    },
    {
        "id": "company-8",
        "title": "Inspect Company Device",
        "command": "/company device SmartAsset_9b47fedc",
        "category": "Company PoC",
        "is_default": 1,
    },
    {
        "id": "company-9",
        "title": "Device + Redis/HTTP Investigation",
        "command": "Investigate disconnected company devices, then check Redis and HTTP health for possible infrastructure pressure.",
        "category": "IOA v3 Mixed Ops",
        "is_default": 1,
    },
    {
        "id": "company-10",
        "title": "Temperature + Platform Workflow",
        "command": "Find company temperature alert evidence and measured values, then check Kubernetes and RabbitMQ health before suggesting next actions.",
        "category": "IOA v3 Mixed Ops",
        "is_default": 1,
    },
]


def list_prompts(user_id):
    return DEFAULT_PROMPTS + get_prompts(user_id)


def get_default_prompt_command(prompt_id):
    for prompt in DEFAULT_PROMPTS:
        if prompt["id"] == prompt_id:
            return prompt["command"]

    return None


def create_user_prompt(user_id, title, command, category):
    prompt_id = create_prompt(user_id, title, command, category)
    return {
        "id": prompt_id,
        "title": title,
        "command": command,
        "category": category,
        "is_default": 0,
    }


def update_user_prompt(prompt_id, user_id, title, command, category):
    return update_prompt(prompt_id, user_id, title, command, category)


def delete_user_prompt(prompt_id, user_id):
    return delete_prompt(prompt_id, user_id)
