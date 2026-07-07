import re

from storage.relational_store import (
    create_prompt,
    delete_prompt,
    get_prompts,
    get_user_data_source_policy,
    update_prompt,
)
from services.company_data_service import company_db_type


MONGO_PROD_DEFAULT_TAGS = {
    "onem2m",
    "runbook",
    "operations_diagnostics",
    "infrastructure_overview",
}


PROMPT_SHORTCUTS = {
    "default-1": "/kpi",
    "default-2": "/coverage",
    "default-3": "/ingestion",
    "default-4": "/api-health",
    "default-5": "/infra",
    "default-6": "/alerts",
    "default-7": "/threshold",
    "company-1": "/company-fleet",
    "company-2": "/company-inventory",
    "company-3": "/company-coverage",
    "company-4": "/company-alerts",
    "company-5": "/company-disconnected",
    "company-6": "/company-temperature",
    "company-7": "/company-rules",
    "company-8": "/company-device",
    "company-9": "/company-redis-http",
    "company-10": "/company-platform",
    "onem2m-1": "/cmd",
    "onem2m-2": "/telemetry",
    "onem2m-3": "/resources",
    "onem2m-4": "/rabbitmq",
    "onem2m-5": "/queue-trend",
    "onem2m-6": "/emqx-dropped",
    "onem2m-7": "/reconnect",
    "onem2m-8": "/k8s",
    "simulator-1": "/sim-fleet",
    "simulator-2": "/sim-device",
    "simulator-3": "/sim-alarms",
    "simulator-4": "/sim-stress",
    "simulator-5": "/sim-smoke",
}


def prompt_shortcut(prompt):
    configured = PROMPT_SHORTCUTS.get(str(prompt.get("id")))

    if configured:
        return configured

    title = str(prompt.get("title") or "prompt").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", title).strip("-")
    return f"/{slug[:32] or 'prompt'}"


def is_default_prompt(prompt):
    value = prompt.get("is_default")

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}

    return bool(value)


def enrich_prompt(prompt):
    enriched = dict(prompt)

    if is_default_prompt(enriched):
        enriched["shortcut"] = prompt_shortcut(enriched)
    else:
        enriched.pop("shortcut", None)

    return enriched


SIMULATOR_PROMPTS = [
    {
        "id": "simulator-1",
        "title": "Simulator Fleet Status",
        "command": (
            "Check the simulator fleet status. Summarize total devices, healthy, "
            "warning, critical, active alarms, and the next simple diagnostic step."
        ),
        "category": "Simulator",
        "tags": ["simulator"],
        "is_default": 1,
    },
    {
        "id": "simulator-2",
        "title": "Simulator Device Check",
        "command": (
            "Diagnose simulator device <device_id>. Check latest status, CPU, "
            "memory, heartbeat delay, alarm state, and recent history."
        ),
        "category": "Simulator",
        "tags": ["simulator"],
        "is_default": 1,
    },
    {
        "id": "simulator-3",
        "title": "Simulator Active Alarms",
        "command": (
            "Show simulator warning and critical alarms. Group them by severity "
            "and suggest which demo device to inspect first."
        ),
        "category": "Simulator",
        "tags": ["simulator"],
        "is_default": 1,
    },
    {
        "id": "simulator-4",
        "title": "Simulator Resource Stress",
        "command": (
            "Find simulator devices with high CPU, high memory, or heartbeat "
            "delay. Explain whether the demo data indicates resource stress."
        ),
        "category": "Simulator",
        "tags": ["simulator"],
        "is_default": 1,
    },
    {
        "id": "simulator-5",
        "title": "Simulator Fallback Smoke Test",
        "command": (
            "Run a simple simulator fallback smoke test: list sample devices, "
            "active alarms, source label, and confirm this is not company MongoDB evidence."
        ),
        "category": "Simulator",
        "tags": ["simulator"],
        "is_default": 1,
    },
]


DEFAULT_PROMPTS = [
    {
        "id": "default-1",
        "title": "Core KPI Overview",
        "command": "Review core IoT platform KPIs: availability, connected devices rate, ingestion health, API success, and any data quality gaps.",
        "category": "KPI Core",
        "tags": ["legacy", "kpi"],
        "is_default": 1,
    },
    {
        "id": "default-2",
        "title": "Connectivity Coverage",
        "command": "Check company device connectivity coverage, disconnected devices, and telemetry coverage gaps.",
        "category": "KPI Core",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "default-3",
        "title": "Ingestion Queue Health",
        "command": "Check RabbitMQ queue backlog and throughput, then explain whether ingestion pressure may affect telemetry freshness.",
        "category": "Ingestion",
        "tags": ["operations_diagnostics", "infrastructure"],
        "is_default": 1,
    },
    {
        "id": "default-4",
        "title": "API Health KPI",
        "command": "Check HTTP API success, 5xx errors, and p95 latency against the platform KPI guidance.",
        "category": "API & Application",
        "tags": ["operations_diagnostics", "infrastructure"],
        "is_default": 1,
    },
    {
        "id": "default-5",
        "title": "Infrastructure Drilldown",
        "command": "Check Kubernetes, Linux node, Redis, MongoDB, and MySQL health as diagnostic evidence for platform issues.",
        "category": "Operations Diagnostics",
        "tags": ["operations_diagnostics", "infrastructure", "infrastructure_overview"],
        "is_default": 1,
    },
    {
        "id": "default-6",
        "title": "Alert Readiness",
        "command": "Review company rule readiness, provisional alert evidence, and the remaining Grafana integration gaps.",
        "category": "Alerts",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "default-7",
        "title": "Manual Threshold Scan",
        "command": "Scan company telemetry payloads for measured values above a specified threshold, then state that this is not an official alert rule.",
        "category": "Data Quality",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-1",
        "title": "Company Fleet Snapshot",
        "command": "/company fleet snapshot",
        "category": "Company PoC",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-2",
        "title": "Company Device Inventory",
        "command": "/company inventory and node overview",
        "category": "Company PoC",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-3",
        "title": "Telemetry Coverage",
        "command": "/company telemetry coverage and unmapped records",
        "category": "Company PoC",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-4",
        "title": "Provisional PoC Alerts",
        "command": "/company provisional alerts with evidence",
        "category": "Company PoC",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-5",
        "title": "Disconnected Company Devices",
        "command": "/company disconnected devices",
        "category": "Company PoC",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-6",
        "title": "High Temperature Findings",
        "command": "/company temperature alerts and measured values",
        "category": "Company PoC",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-7",
        "title": "Rule Integration Readiness",
        "command": "/company rule readiness and Grafana gaps",
        "category": "Company PoC",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-8",
        "title": "Inspect Company Device",
        "command": "/company device SmartAsset_9b47fedc",
        "category": "Company PoC",
        "tags": ["legacy", "company_poc"],
        "is_default": 1,
    },
    {
        "id": "company-9",
        "title": "Device + Redis/HTTP Investigation",
        "command": "Investigate disconnected company devices, then check Redis and HTTP health for possible infrastructure pressure.",
        "category": "IOA v3 Mixed Ops",
        "tags": ["legacy", "company_poc", "infrastructure"],
        "is_default": 1,
    },
    {
        "id": "company-10",
        "title": "Temperature + Platform Workflow",
        "command": "Find company temperature alert evidence and measured values, then check Kubernetes and RabbitMQ health before suggesting next actions.",
        "category": "IOA v3 Mixed Ops",
        "tags": ["legacy", "company_poc", "infrastructure"],
        "is_default": 1,
    },
    {
        "id": "onem2m-1",
        "title": "Command Downlink Debug",
        "command": (
            "Debug why device <device_id> did not receive a command. "
            "Treat <device_id> as the only required operator input. Derive AE ID "
            "and request/correlation IDs from MongoDB resources, URI mapper, "
            "latest command CIN records, and adapter/core logs. Check iot-http-api "
            "and iot-mqtt-client-adapter logs, core logs, IDENTITY, AE, cnt_command, "
            "SUBSCRIPTION, URI_MAPPER, and latest command CIN evidence. Summarize "
            "the most likely failure point, supporting evidence, evidence gaps, "
            "and the next action."
        ),
        "category": "OneM2M Ops",
        "tags": ["onem2m", "runbook"],
        "is_default": 1,
    },
    {
        "id": "onem2m-2",
        "title": "Telemetry Uplink Debug",
        "command": (
            "Debug why telemetry from device <device_id> did not reach the backend. "
            "Treat <device_id> as the only required operator input. Derive AE ID "
            "and request/correlation IDs from MongoDB resources, URI mapper, "
            "latest telemetry CIN records, adapter logs, and notify logs. Check "
            "iot-http-api and iot-mqtt-client-adapter logs, cnt_telemetry, latest "
            "telemetry CIN evidence, backend SUBSCRIPTION, notify logs, and relevant "
            "EMQX/RabbitMQ evidence. Do not mark any resource as present unless it "
            "is found in DB or log evidence. Summarize the most likely failure point, "
            "supporting evidence, evidence gaps, and the next action."
        ),
        "category": "OneM2M Ops",
        "tags": ["onem2m", "runbook"],
        "is_default": 1,
    },
    {
        "id": "onem2m-3",
        "title": "Device Resource Check",
        "command": (
            "Check whether device <device_id> is registered on the platform and "
            "whether its required OneM2M resources exist. Treat <device_id> as the "
            "only required operator input. Derive AE ID and request/correlation IDs "
            "from MongoDB resources and logs when needed. Check iot-http-api and "
            "iot-mqtt-client-adapter logs, then verify IDENTITY, AE, CNT, CIN, "
            "SUBSCRIPTION, and URI_MAPPER evidence. List exactly which resources "
            "exist, which are missing, what evidence supports each status, and the "
            "next action."
        ),
        "category": "OneM2M Ops",
        "tags": ["onem2m", "runbook"],
        "is_default": 1,
    },
    {
        "id": "onem2m-4",
        "title": "RabbitMQ Top Backlog",
        "command": (
            "Find the top 10 RabbitMQ queues by message backlog in namespace test. "
            "Use the metric topk(10, sum by (queue) "
            "(rabbitmq_queue_messages{namespace=\"test\",job=\"monitoring/rabbitmq\"})), flag any queue above "
            "10000 messages, then answer with the highest queue, message count, "
            "normal/abnormal assessment, and consumer/service follow-up."
        ),
        "category": "Operations Diagnostics",
        "tags": ["onem2m", "runbook", "infrastructure"],
        "is_default": 1,
    },
    {
        "id": "onem2m-5",
        "title": "RabbitMQ Linear Queue Growth",
        "command": (
            "Check whether RabbitMQ queue messages are increasing linearly over "
            "the requested time range. Use sum by (queue) "
            "(rabbitmq_queue_messages{namespace=\"test\",job=\"monitoring/rabbitmq\"}) with start, end, and "
            "step when provided. Conclude whether consumer capacity or service "
            "errors are likely and list the next pod/log/CPU/memory checks."
        ),
        "category": "Operations Diagnostics",
        "tags": ["onem2m", "runbook", "infrastructure"],
        "is_default": 1,
    },
    {
        "id": "onem2m-6",
        "title": "EMQX Dropped Messages",
        "command": (
            "Check whether EMQX messages dropped increased over the requested "
            "time range. Use sum(emqx_messages_dropped{namespace=\"emqx\",job=\"emqx\"}) "
            "and then recommend checking EMQX logs, MQTT adapter logs, broker "
            "CPU/memory, connection count, queue backlog, and core service errors."
        ),
        "category": "Operations Diagnostics",
        "tags": ["onem2m", "runbook", "infrastructure"],
        "is_default": 1,
    },
    {
        "id": "onem2m-7",
        "title": "EMQX Reconnect Trend",
        "command": (
            "Check EMQX client connected and disconnected rates to detect "
            "onboarding spikes or reconnect loops. Do not require a device_id "
            "from the operator; derive affected device candidates from EMQX or "
            "MQTT adapter evidence when available. Use "
            "sum(rate(emqx_client_connected{namespace=\"emqx\",job=\"emqx\"}[1m])) "
            "and sum(rate(emqx_client_disconnected{namespace=\"emqx\",job=\"emqx\"}[1m])). "
            "Then suggest MQTT adapter log, device resource, previous-error-log, "
            "and EMQX broker follow-up."
        ),
        "category": "Operations Diagnostics",
        "tags": ["onem2m", "runbook", "infrastructure"],
        "is_default": 1,
    },
    {
        "id": "onem2m-8",
        "title": "Kubernetes Resource Debug",
        "command": (
            "Check Kubernetes resource health in namespace one-iot: pod CPU, "
            "memory, restart count, pod status, node resources, namespace resources, "
            "and latest service error logs. Identify abnormal service/pod, high "
            "CPU/memory, restart count, OOMKilled, CrashLoopBackOff, and next action."
        ),
        "category": "Operations Diagnostics",
        "tags": ["onem2m", "runbook", "infrastructure"],
        "is_default": 1,
    },
]


def resolve_prompt_data_source(user_id, selected_source=None):
    if selected_source in {"simulator", "company"}:
        return selected_source

    policy = get_user_data_source_policy(user_id)
    default_source = policy.get("default_data_source", "simulator")
    allowed_sources = set(policy.get("allowed_data_sources") or ["simulator"])

    if default_source in allowed_sources:
        return default_source

    return "simulator"


def mongo_prod_prompt_catalog_active():
    return company_db_type() == "mongodb"


def default_prompt_allowed(prompt, selected_source):
    if selected_source == "simulator":
        return "simulator" in set(prompt.get("tags") or [])

    if not mongo_prod_prompt_catalog_active():
        return True

    return bool(set(prompt.get("tags") or []) & MONGO_PROD_DEFAULT_TAGS)


def prompt_sort_key(prompt):
    tags = set(prompt.get("tags") or [])

    if "simulator" in tags:
        group = 0
    elif "runbook" in tags:
        group = 0
    elif "operations_diagnostics" in tags:
        group = 1
    elif "infrastructure" in tags:
        group = 2
    elif "onem2m" in tags:
        group = 3
    elif prompt.get("is_default"):
        group = 4
    else:
        group = 5

    return (group, str(prompt.get("id")))


def list_prompts(user_id, selected_source=None):
    selected_source = resolve_prompt_data_source(user_id, selected_source)
    base_prompts = SIMULATOR_PROMPTS if selected_source == "simulator" else DEFAULT_PROMPTS
    default_prompts = [
        prompt
        for prompt in base_prompts
        if default_prompt_allowed(prompt, selected_source)
    ]

    if selected_source == "simulator":
        return [
            enrich_prompt(prompt)
            for prompt in sorted(default_prompts, key=prompt_sort_key)
        ]

    user_prompts = [
        prompt
        for prompt in get_prompts(user_id)
        if not prompt.get("is_default")
    ]
    return [
        enrich_prompt(prompt)
        for prompt in sorted(default_prompts, key=prompt_sort_key) + user_prompts
    ]


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
