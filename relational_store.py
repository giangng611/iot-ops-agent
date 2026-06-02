from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

import database as sqlite_store
from postgres_store import get_postgres_connection, postgres_enabled

_last_fallback = None


def using_postgres():
    return postgres_enabled()


def get_app_db_backend():
    return "supabase" if using_postgres() else "sqlite"


def get_last_fallback():
    return _last_fallback


def _with_fallback(operation_name, postgres_operation, sqlite_operation):
    if not using_postgres():
        return sqlite_operation()

    try:
        return postgres_operation()
    except Exception as exc:
        global _last_fallback

        _last_fallback = {
            "operation": operation_name,
            "error": str(exc),
            "fallback_backend": "sqlite",
        }
        print(
            f"Supabase/Postgres app-data {operation_name} failed; "
            f"falling back to SQLite: {exc}"
        )
        return sqlite_operation()


def get_storage_status():
    status = {
        "app_data": {
            "configured_backend": get_app_db_backend(),
            "active_backend": get_app_db_backend(),
            "fallback_backend": "sqlite",
            "healthy": True,
            "last_fallback": get_last_fallback(),
        }
    }

    if not using_postgres():
        status["app_data"]["message"] = "SQLite app-data backend is active."
        return status

    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("select 1 as ok")
                cursor.fetchone()
    except Exception as exc:
        status["app_data"].update({
            "active_backend": "sqlite",
            "healthy": False,
            "message": (
                "Supabase/Postgres is configured but unavailable; "
                "SQLite fallback is active."
            ),
            "error": str(exc),
        })
        return status

    status["app_data"]["message"] = "Supabase/Postgres app-data backend is healthy."
    return status


def init_db():
    sqlite_store.init_db()


def create_chat(user_id, title):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.chats (user_id, title, created_at)
                    values (%s, %s, %s)
                    returning id
                    """,
                    (
                        user_id,
                        title,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                chat_id = cursor.fetchone()["id"]
            conn.commit()
            return chat_id

    return _with_fallback(
        "create_chat",
        postgres_operation,
        lambda: sqlite_store.create_chat(user_id, title),
    )


def get_chats(user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select id, title, created_at, is_pinned
                    from public.chats
                    where user_id = %s
                    order by is_pinned desc, id desc
                    """,
                    (user_id,),
                )
                rows = cursor.fetchall()

        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "is_pinned": bool(row["is_pinned"]),
            }
            for row in rows
        ]

    return _with_fallback(
        "get_chats",
        postgres_operation,
        lambda: sqlite_store.get_chats(user_id),
    )


def chat_belongs_to_user(chat_id, user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select 1
                    from public.chats
                    where id = %s
                    and user_id = %s
                    limit 1
                    """,
                    (chat_id, user_id),
                )
                return cursor.fetchone() is not None

    return _with_fallback(
        "chat_belongs_to_user",
        postgres_operation,
        lambda: sqlite_store.chat_belongs_to_user(chat_id, user_id),
    )


def add_message(chat_id, role, content, reasoning_steps=None):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.messages (
                        chat_id,
                        role,
                        content,
                        reasoning_steps,
                        created_at
                    )
                    values (%s, %s, %s, %s, %s)
                    """,
                    (
                        chat_id,
                        role,
                        content,
                        reasoning_steps,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            conn.commit()

    return _with_fallback(
        "add_message",
        postgres_operation,
        lambda: sqlite_store.add_message(chat_id, role, content, reasoning_steps),
    )


def get_messages(chat_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select role, content, reasoning_steps, created_at
                    from public.messages
                    where chat_id = %s
                    order by id asc
                    """,
                    (chat_id,),
                )
                rows = cursor.fetchall()

        return [
            {
                "role": row["role"],
                "content": row["content"],
                "reasoning_steps": row["reasoning_steps"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    return _with_fallback(
        "get_messages",
        postgres_operation,
        lambda: sqlite_store.get_messages(chat_id),
    )


def create_user(username, password):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.users (username, password_hash, created_at)
                    values (%s, %s, %s)
                    """,
                    (
                        username,
                        generate_password_hash(password),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            conn.commit()

    return _with_fallback(
        "create_user",
        postgres_operation,
        lambda: sqlite_store.create_user(username, password),
    )


def get_user_by_username(username):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select id, username, password_hash
                    from public.users
                    where username = %s
                    """,
                    (username,),
                )
                row = cursor.fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
        }

    return _with_fallback(
        "get_user_by_username",
        postgres_operation,
        lambda: sqlite_store.get_user_by_username(username),
    )


def verify_user(username, password):
    user = get_user_by_username(username)

    if not user:
        return None

    if not check_password_hash(user["password_hash"], password):
        return None

    return user


def delete_chat(chat_id, user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    delete from public.chats
                    where id = %s
                    and user_id = %s
                    """,
                    (chat_id, user_id),
                )
                deleted = cursor.rowcount
            conn.commit()
            return deleted > 0

    return _with_fallback(
        "delete_chat",
        postgres_operation,
        lambda: sqlite_store.delete_chat(chat_id, user_id),
    )


def toggle_pin_chat(chat_id, user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select is_pinned
                    from public.chats
                    where id = %s
                    and user_id = %s
                    """,
                    (chat_id, user_id),
                )
                row = cursor.fetchone()

                if not row:
                    return None

                new_value = not bool(row["is_pinned"])
                cursor.execute(
                    """
                    update public.chats
                    set is_pinned = %s
                    where id = %s
                    and user_id = %s
                    """,
                    (new_value, chat_id, user_id),
                )
            conn.commit()
            return new_value

    return _with_fallback(
        "toggle_pin_chat",
        postgres_operation,
        lambda: sqlite_store.toggle_pin_chat(chat_id, user_id),
    )


def change_user_password(user_id, current_password, new_password):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select password_hash
                    from public.users
                    where id = %s
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()

                if not row:
                    return False, "User not found"

                if not check_password_hash(row["password_hash"], current_password):
                    return False, "Current password is incorrect"

                cursor.execute(
                    """
                    update public.users
                    set password_hash = %s
                    where id = %s
                    """,
                    (generate_password_hash(new_password), user_id),
                )
            conn.commit()
            return True, "Password updated successfully"

    return _with_fallback(
        "change_user_password",
        postgres_operation,
        lambda: sqlite_store.change_user_password(
            user_id,
            current_password,
            new_password,
        ),
    )


def get_prompts(user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select id, title, command, category, is_default
                    from public.prompts
                    where user_id = %s or is_default = true
                    order by is_default desc, id desc
                    """,
                    (user_id,),
                )
                rows = cursor.fetchall()

        return [
            {
                "id": row["id"],
                "title": row["title"],
                "command": row["command"],
                "category": row["category"],
                "is_default": bool(row["is_default"]),
            }
            for row in rows
        ]

    return _with_fallback(
        "get_prompts",
        postgres_operation,
        lambda: sqlite_store.get_prompts(user_id),
    )


def create_prompt(user_id, title, command, category):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.prompts (
                        user_id,
                        title,
                        command,
                        category,
                        is_default
                    )
                    values (%s, %s, %s, %s, false)
                    returning id
                    """,
                    (user_id, title, command, category),
                )
                prompt_id = cursor.fetchone()["id"]
            conn.commit()
            return prompt_id

    return _with_fallback(
        "create_prompt",
        postgres_operation,
        lambda: sqlite_store.create_prompt(user_id, title, command, category),
    )


def update_prompt(prompt_id, user_id, title, command, category):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    update public.prompts
                    set title = %s,
                        command = %s,
                        category = %s
                    where id = %s
                    and user_id = %s
                    and is_default = false
                    """,
                    (title, command, category, prompt_id, user_id),
                )
                updated = cursor.rowcount
            conn.commit()
            return updated > 0

    return _with_fallback(
        "update_prompt",
        postgres_operation,
        lambda: sqlite_store.update_prompt(
            prompt_id,
            user_id,
            title,
            command,
            category,
        ),
    )


def delete_prompt(prompt_id, user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    delete from public.prompts
                    where id = %s
                    and user_id = %s
                    and is_default = false
                    """,
                    (prompt_id, user_id),
                )
                deleted = cursor.rowcount
            conn.commit()
            return deleted > 0

    return _with_fallback(
        "delete_prompt",
        postgres_operation,
        lambda: sqlite_store.delete_prompt(prompt_id, user_id),
    )


def update_username(user_id, new_username):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    update public.users
                    set username = %s
                    where id = %s
                    """,
                    (new_username, user_id),
                )
                updated = cursor.rowcount
            conn.commit()
            return updated > 0

    return _with_fallback(
        "update_username",
        postgres_operation,
        lambda: sqlite_store.update_username(user_id, new_username),
    )


def delete_user_account(user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    delete from public.prompts
                    where user_id = %s
                    and is_default = false
                    """,
                    (user_id,),
                )
                cursor.execute(
                    """
                    delete from public.users
                    where id = %s
                    """,
                    (user_id,),
                )
                deleted = cursor.rowcount
            conn.commit()
            return deleted > 0

    return _with_fallback(
        "delete_user_account",
        postgres_operation,
        lambda: sqlite_store.delete_user_account(user_id),
    )


def get_user_usage_stats(user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "select count(*) as count from public.chats where user_id = %s",
                    (user_id,),
                )
                chat_count = cursor.fetchone()["count"]

                cursor.execute(
                    """
                    select count(*) as count
                    from public.messages
                    where chat_id in (
                        select id from public.chats where user_id = %s
                    )
                    """,
                    (user_id,),
                )
                message_count = cursor.fetchone()["count"]

                cursor.execute(
                    """
                    select count(*) as count
                    from public.prompts
                    where user_id = %s
                    and is_default = false
                    """,
                    (user_id,),
                )
                custom_prompt_count = cursor.fetchone()["count"]

        try:
            from telemetry_store import get_all_latest_devices

            device_count = len(get_all_latest_devices())
        except Exception:
            device_count = sqlite_store.get_user_usage_stats(user_id)["device_count"]

        return {
            "chat_count": chat_count,
            "message_count": message_count,
            "custom_prompt_count": custom_prompt_count,
            "device_count": device_count,
        }

    return _with_fallback(
        "get_user_usage_stats",
        postgres_operation,
        lambda: sqlite_store.get_user_usage_stats(user_id),
    )
