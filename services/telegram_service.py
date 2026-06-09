import json
import os

import requests

from services.chat_service import save_chat_message
from storage.relational_store import create_chat


TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_TELEGRAM_MESSAGE_CHARS = 3900


def telegram_enabled():
    return bool(os.getenv("TELEGRAM_BOT_TOKEN"))


def get_telegram_secret_token():
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()


def telegram_secret_is_valid(request_secret):
    expected_secret = get_telegram_secret_token()

    if not expected_secret:
        return True

    return request_secret == expected_secret


def extract_message(update):
    if not isinstance(update, dict):
        return None

    message = update.get("message") or update.get("edited_message")

    if not isinstance(message, dict):
        return None

    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")

    if not text or chat_id is None:
        return None

    return {
        "chat_id": chat_id,
        "telegram_user_id": sender.get("id"),
        "telegram_username": sender.get("username"),
        "text": text,
    }


def get_allowed_telegram_user_ids():
    raw_value = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()

    if not raw_value:
        return set()

    return {
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    }


def telegram_user_is_allowed(telegram_user_id):
    allowed_user_ids = get_allowed_telegram_user_ids()

    if not allowed_user_ids:
        return True

    return str(telegram_user_id) in allowed_user_ids


def build_help_text():
    return "\n".join([
        "IoT Ops Agent commands:",
        "/overview system health",
        "/check all unhealthy devices",
        "/show devices with alarms",
        "/diagnose system issue",
        "/check devices with delayed heartbeat",
        "/diagnose gateway-001",
    ])


def normalize_telegram_prompt(text):
    if text in {"/", "/start", "/help"}:
        return None, build_help_text()

    return text, None


def split_telegram_text(text):
    if len(text) <= MAX_TELEGRAM_MESSAGE_CHARS:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        chunks.append(remaining[:MAX_TELEGRAM_MESSAGE_CHARS])
        remaining = remaining[MAX_TELEGRAM_MESSAGE_CHARS:]

    return chunks


def send_telegram_message(chat_id, text):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

    for chunk in split_telegram_text(text):
        response = requests.post(
            f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()


def get_history_user_id():
    raw_value = os.getenv("TELEGRAM_HISTORY_USER_ID", "").strip()

    if not raw_value:
        return None

    try:
        return int(raw_value)
    except ValueError:
        return None


def make_chat_title(message):
    compact_message = " ".join(message.split())

    if len(compact_message) > 48:
        compact_message = f"{compact_message[:45]}..."

    return f"Telegram: {compact_message or 'New request'}"


def save_telegram_history(message, result):
    user_id = get_history_user_id()

    if user_id is None:
        return None

    chat_id = create_chat(user_id, make_chat_title(message["text"]))
    save_chat_message(
        chat_id=chat_id,
        user_id=user_id,
        role="user",
        content=message["text"],
    )
    save_chat_message(
        chat_id=chat_id,
        user_id=user_id,
        role="assistant",
        content=result["final_answer"],
        reasoning_steps=result.get("steps"),
        token_usage=result.get("token_usage"),
    )

    return chat_id


def handle_telegram_update(update, langgraph_agent):
    message = extract_message(update)

    if message is None:
        return {"status": "ignored"}

    if not telegram_user_is_allowed(message["telegram_user_id"]):
        send_telegram_message(
            message["chat_id"],
            "You are not allowed to use this IoT Ops Agent bot.",
        )
        return {"status": "forbidden"}

    prompt, help_text = normalize_telegram_prompt(message["text"])

    if help_text:
        send_telegram_message(message["chat_id"], help_text)
        return {"status": "help_sent"}

    result = langgraph_agent.run(prompt)
    final_answer = result.get("final_answer") or "No answer was generated."
    history_chat_id = save_telegram_history(message, {
        "final_answer": final_answer,
        "steps": result.get("steps", []),
        "token_usage": result.get("token_usage"),
    })

    send_telegram_message(message["chat_id"], final_answer)

    return {
        "status": "answered",
        "history_chat_id": history_chat_id,
        "step_count": len(result.get("steps", [])),
    }


def build_set_webhook_payload(public_base_url):
    secret_token = get_telegram_secret_token()
    payload = {
        "url": f"{public_base_url.rstrip('/')}/api/telegram/webhook",
        "allowed_updates": json.dumps(["message", "edited_message"]),
    }

    if secret_token:
        payload["secret_token"] = secret_token

    return payload
