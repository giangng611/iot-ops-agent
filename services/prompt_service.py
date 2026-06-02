from storage.relational_store import (
    create_prompt,
    delete_prompt,
    get_prompts,
    update_prompt,
)


DEFAULT_PROMPTS = [
    {
        "id": "default-1",
        "title": "System Health Overview",
        "command": "/overview system health",
        "category": "Fleet",
        "is_default": 1,
    },
    {
        "id": "default-2",
        "title": "Check Unhealthy Devices",
        "command": "/check all unhealthy devices",
        "category": "Fleet",
        "is_default": 1,
    },
    {
        "id": "default-3",
        "title": "Find Critical Devices",
        "command": "/find critical devices",
        "category": "Alerts",
        "is_default": 1,
    },
    {
        "id": "default-4",
        "title": "Diagnose System Issue",
        "command": "/diagnose system issue",
        "category": "Diagnostics",
        "is_default": 1,
    },
    {
        "id": "default-5",
        "title": "Check Heartbeat Delays",
        "command": "/check devices with delayed heartbeat",
        "category": "Fleet",
        "is_default": 1,
    },
    {
        "id": "default-6",
        "title": "Show Active Alarms",
        "command": "/show devices with alarms",
        "category": "Alerts",
        "is_default": 1,
    },
]


def list_prompts(user_id):
    return DEFAULT_PROMPTS + get_prompts(user_id)


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
