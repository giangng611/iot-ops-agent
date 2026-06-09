import json

from prompts import CHAT_TITLE_PROMPT
from storage.relational_store import (
    add_message,
    chat_belongs_to_user,
    create_chat,
    delete_chat,
    get_chats,
    get_messages,
    toggle_pin_chat,
)


def extract_token_usage_from_reasoning_steps(reasoning_steps):
    if not isinstance(reasoning_steps, list):
        return None

    for step in reversed(reasoning_steps):
        if not isinstance(step, dict):
            continue

        output = step.get("output")

        if isinstance(output, dict):
            token_usage = output.get("token_usage")

            if isinstance(token_usage, dict) and token_usage.get("total_tokens"):
                return token_usage

        token_usage = step.get("token_usage")

        if isinstance(token_usage, dict) and token_usage.get("total_tokens"):
            return token_usage

    return None


def parse_token_count(value):
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_token_usage(token_usage):
    if isinstance(token_usage, str):
        try:
            token_usage = json.loads(token_usage)
        except ValueError:
            return None

    if not isinstance(token_usage, dict):
        return None

    usage = (
        token_usage.get("usage")
        if isinstance(token_usage.get("usage"), dict)
        else token_usage
    )

    input_tokens = parse_token_count(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("promptTokens")
        or usage.get("prompt_tokens_used")
    )
    output_tokens = parse_token_count(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("completionTokens")
        or usage.get("completion_tokens_used")
    )
    total_tokens = parse_token_count(
        usage.get("total_tokens")
        or usage.get("totalTokens")
        or usage.get("total_tokens_used")
    )

    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    if total_tokens is None:
        return None

    normalized = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }

    if usage.get("source"):
        normalized["source"] = usage["source"]

    for metadata_key in ("runtime_label", "model_name"):
        if usage.get(metadata_key):
            normalized[metadata_key] = usage[metadata_key]

    return normalized


def generate_chat_title(openai_client, user_message):
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": CHAT_TITLE_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
            temperature=0.2,
            max_tokens=20,
        )

        title = response.choices[0].message.content.strip()

        if not title:
            return "New analysis"

        return title[:60]
    except Exception:
        return "New analysis"


def list_chats(user_id):
    return get_chats(user_id)


def create_user_chat(user_id, message, openai_client):
    title = generate_chat_title(openai_client, message)
    chat_id = create_chat(user_id, title)
    return chat_id, title


def get_chat_messages(chat_id, user_id):
    if not chat_belongs_to_user(chat_id, user_id):
        return None

    return get_messages(chat_id)


def save_chat_message(
    chat_id,
    user_id,
    role,
    content,
    reasoning_steps=None,
    token_usage=None,
):
    if not chat_belongs_to_user(chat_id, user_id):
        return False, "Chat not found", 404

    if not role or not content:
        return False, "role and content are required", 400

    if token_usage is None:
        token_usage = extract_token_usage_from_reasoning_steps(reasoning_steps)

    token_usage = normalize_token_usage(token_usage)

    if token_usage is not None:
        token_usage = json.dumps(token_usage)

    if reasoning_steps is not None:
        reasoning_steps = json.dumps(reasoning_steps)

    add_message(
        chat_id=chat_id,
        role=role,
        content=content,
        reasoning_steps=reasoning_steps,
        token_usage=token_usage,
    )
    return True, "saved", 200


def remove_chat(chat_id, user_id):
    return delete_chat(chat_id, user_id)


def toggle_chat_pin(chat_id, user_id):
    return toggle_pin_chat(chat_id, user_id)
