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


def save_chat_message(chat_id, user_id, role, content, reasoning_steps=None):
    if not chat_belongs_to_user(chat_id, user_id):
        return False, "Chat not found", 404

    if not role or not content:
        return False, "role and content are required", 400

    if reasoning_steps is not None:
        reasoning_steps = json.dumps(reasoning_steps)

    add_message(
        chat_id=chat_id,
        role=role,
        content=content,
        reasoning_steps=reasoning_steps,
    )
    return True, "saved", 200


def remove_chat(chat_id, user_id):
    return delete_chat(chat_id, user_id)


def toggle_chat_pin(chat_id, user_id):
    return toggle_pin_chat(chat_id, user_id)
