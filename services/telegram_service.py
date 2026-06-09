import json
import os
import threading
import time
from collections import OrderedDict

import requests

from services.chat_service import save_chat_message
from storage.relational_store import create_chat


TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_TELEGRAM_MESSAGE_CHARS = 3900
_telegram_update_lock = threading.Lock()
_telegram_updates_inflight = set()
_telegram_updates_processed = OrderedDict()


def claim_telegram_update(update):
    update_id = update.get("update_id") if isinstance(update, dict) else None

    if update_id is None:
        return None, True

    update_key = str(update_id)
    retention_seconds = int(
        os.getenv("TELEGRAM_UPDATE_RETENTION_SECONDS", "86400")
    )
    cutoff = time.monotonic() - retention_seconds

    with _telegram_update_lock:
        while _telegram_updates_processed:
            _, processed_at = next(iter(_telegram_updates_processed.items()))

            if processed_at >= cutoff:
                break

            _telegram_updates_processed.popitem(last=False)

        if (
            update_key in _telegram_updates_inflight
            or update_key in _telegram_updates_processed
        ):
            return update_key, False

        _telegram_updates_inflight.add(update_key)

    return update_key, True


def complete_telegram_update(update_key):
    if update_key is None:
        return

    with _telegram_update_lock:
        _telegram_updates_inflight.discard(update_key)
        _telegram_updates_processed[update_key] = time.monotonic()

        while len(_telegram_updates_processed) > 2048:
            _telegram_updates_processed.popitem(last=False)


def release_telegram_update(update_key):
    if update_key is None:
        return

    with _telegram_update_lock:
        _telegram_updates_inflight.discard(update_key)


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


def start_telegram_history(message):
    user_id = get_history_user_id()

    if user_id is None:
        return None, None

    chat_id = create_chat(user_id, make_chat_title(message["text"]))
    save_chat_message(
        chat_id=chat_id,
        user_id=user_id,
        role="user",
        content=message["text"],
    )

    return user_id, chat_id


def finish_telegram_history(user_id, chat_id, result):
    if user_id is None or chat_id is None:
        return

    save_chat_message(
        chat_id=chat_id,
        user_id=user_id,
        role="assistant",
        content=result["final_answer"],
        reasoning_steps=result.get("steps"),
        token_usage=result.get("token_usage"),
    )


def merge_stream_event(steps, event):
    if event.get("type") == "thought":
        step = next(
            (
                item for item in steps
                if item.get("iteration") == event.get("iteration")
            ),
            None,
        )
        values = {
            "iteration": event.get("iteration"),
            "thought": event.get("thought"),
            "action": event.get("action"),
            "workflow": event.get("workflow"),
        }

        if step is None:
            steps.append(values)
        else:
            step.update(values)

    if event.get("type") == "observation":
        step = next(
            (
                item for item in steps
                if item.get("iteration") == event.get("iteration")
            ),
            None,
        )

        if step is not None:
            step["output"] = (event.get("observation") or {}).get("output")


def add_telegram_runtime_metadata(token_usage):
    usage = dict(token_usage or {})
    usage["runtime_label"] = "IOA v2 · LangGraph"
    usage["model_name"] = "gpt-4o-mini"
    return usage


def handle_telegram_update(update, langgraph_agent, emit_user_event=None):
    return process_telegram_update(
        update,
        langgraph_agent,
        emit_user_event=emit_user_event,
    )


def process_telegram_update(
    update,
    langgraph_agent,
    emit_user_event=None,
    get_user_data_source=None,
):
    message = extract_message(update)

    if message is None:
        return {"status": "ignored"}

    update_key, claimed = claim_telegram_update(update)

    if not claimed:
        return {"status": "duplicate"}

    try:
        if not telegram_user_is_allowed(message["telegram_user_id"]):
            send_telegram_message(
                message["chat_id"],
                "You are not allowed to use this IoT Ops Agent bot.",
            )
            result = {"status": "forbidden"}
        else:
            prompt, help_text = normalize_telegram_prompt(message["text"])

            if help_text:
                send_telegram_message(message["chat_id"], help_text)
                result = {"status": "help_sent"}
            else:
                history_user_id, history_chat_id = start_telegram_history(
                    message
                )
                title = make_chat_title(message["text"])

                if (
                    emit_user_event
                    and history_user_id is not None
                    and history_chat_id is not None
                ):
                    emit_user_event(
                        history_user_id,
                        "telegram_chat_started",
                        {
                            "chat_id": history_chat_id,
                            "title": title,
                            "message": message["text"],
                        },
                    )

                steps = []
                final_answer = "No answer was generated."
                token_usage = None
                data_source = (
                    get_user_data_source(history_user_id)
                    if get_user_data_source
                    else "simulator"
                )

                for stream_event in langgraph_agent.run_stream(
                    prompt,
                    data_source=data_source,
                ):
                    merge_stream_event(steps, stream_event)

                    if stream_event.get("type") == "final":
                        final_answer = (
                            stream_event.get("final_answer")
                            or final_answer
                        )
                        token_usage = add_telegram_runtime_metadata(
                            stream_event.get("token_usage")
                        )

                    if (
                        emit_user_event
                        and history_user_id is not None
                        and history_chat_id is not None
                    ):
                        emit_user_event(
                            history_user_id,
                            "telegram_reasoning_event",
                            {
                                "chat_id": history_chat_id,
                                "event": stream_event,
                            },
                        )

                agent_result = {
                    "final_answer": final_answer,
                    "steps": steps,
                    "token_usage": token_usage,
                }
                finish_telegram_history(
                    history_user_id,
                    history_chat_id,
                    agent_result,
                )

                if (
                    emit_user_event
                    and history_user_id is not None
                    and history_chat_id is not None
                ):
                    emit_user_event(
                        history_user_id,
                        "telegram_chat_completed",
                        {
                            "chat_id": history_chat_id,
                            "final_answer": final_answer,
                            "steps": steps,
                            "token_usage": token_usage,
                        },
                    )

                send_telegram_message(message["chat_id"], final_answer)
                result = {
                    "status": "answered",
                    "history_chat_id": history_chat_id,
                    "step_count": len(agent_result.get("steps", [])),
                }
    except Exception:
        release_telegram_update(update_key)
        raise

    complete_telegram_update(update_key)
    return result


def process_telegram_update_in_background(
    update,
    langgraph_agent,
    emit_user_event=None,
    get_user_data_source=None,
):
    def run():
        try:
            process_telegram_update(
                update,
                langgraph_agent,
                emit_user_event=emit_user_event,
                get_user_data_source=get_user_data_source,
            )
        except Exception as exc:
            print(f"Telegram background processing failed: {exc}")
            history_user_id = get_history_user_id()

            if emit_user_event and history_user_id is not None:
                emit_user_event(
                    history_user_id,
                    "telegram_chat_failed",
                    {
                        "error": "Telegram request failed.",
                    },
                )

    worker = threading.Thread(
        target=run,
        name=f"telegram-update-{update.get('update_id', 'unknown')}",
        daemon=True,
    )
    worker.start()
    return worker


def build_set_webhook_payload(public_base_url):
    secret_token = get_telegram_secret_token()
    payload = {
        "url": f"{public_base_url.rstrip('/')}/api/telegram/webhook",
        "allowed_updates": json.dumps(["message", "edited_message"]),
    }

    if secret_token:
        payload["secret_token"] = secret_token

    return payload
