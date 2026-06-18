import os
import time

from werkzeug.security import check_password_hash, generate_password_hash
from services.time_service import now_iso

from storage import sqlite_store
from storage.postgres_store import (
    close_postgres_pool,
    get_postgres_connection,
    postgres_enabled,
    postgres_url_configured,
)

_last_fallback = None
_postgres_circuit_open_until = 0.0


def using_postgres():
    return postgres_enabled()


def get_configured_app_db_backend():
    configured_backend = os.getenv("APP_DB_BACKEND")

    if configured_backend:
        return configured_backend.lower()

    if postgres_url_configured():
        return "supabase"

    return "sqlite"


def get_app_db_backend():
    return "supabase" if using_postgres() else "sqlite"


def app_db_fallback_enabled():
    return os.getenv("APP_DB_FALLBACK_ENABLED", "false").lower() == "true"


def get_last_fallback():
    return _last_fallback


def clear_fallback():
    global _last_fallback
    global _postgres_circuit_open_until

    _last_fallback = None
    _postgres_circuit_open_until = 0.0


def safe_error_summary(error):
    if isinstance(error, BaseException):
        return type(error).__name__

    return str(error)


def record_fallback(operation_name, error, fallback_backend="sqlite"):
    global _last_fallback
    global _postgres_circuit_open_until

    _last_fallback = {
        "operation": operation_name,
        "error": safe_error_summary(error),
        "fallback_backend": fallback_backend,
        "recorded_at": now_iso(),
    }
    _postgres_circuit_open_until = (
        time.monotonic()
        + float(os.getenv("POSTGRES_CIRCUIT_BREAKER_SECONDS", "30"))
    )


def postgres_circuit_is_open():
    return time.monotonic() < _postgres_circuit_open_until


def _postgres_retry_allowed(operation_name):
    return (
        operation_name.startswith("get_")
        or operation_name in {
            "chat_belongs_to_user",
            "health_check",
        }
    )


def _looks_like_stale_postgres_connection(error):
    message = str(error).lower()
    stale_markers = [
        "connection is closed",
        "consuming input failed",
        "could not receive data from server",
        "operation timed out",
        "ssl syscall",
        "[bad]",
    ]

    return any(marker in message for marker in stale_markers)


def _looks_like_postgres_timeout(error):
    message = str(error).lower()
    timeout_markers = [
        "couldn't get a connection",
        "operation timed out",
        "timeout expired",
        "query timed out",
        "statement timeout",
        "canceling statement due to statement timeout",
        "another command is already in progress",
    ]

    return any(marker in message for marker in timeout_markers)


def _with_fallback(operation_name, postgres_operation, sqlite_operation):
    if not using_postgres():
        return sqlite_operation()

    if app_db_fallback_enabled() and postgres_circuit_is_open():
        return sqlite_operation()

    try:
        return postgres_operation()
    except Exception as exc:
        if (
            _postgres_retry_allowed(operation_name)
            and _looks_like_stale_postgres_connection(exc)
            and not _looks_like_postgres_timeout(exc)
        ):
            close_postgres_pool()
            try:
                return postgres_operation()
            except Exception as retry_exc:
                exc = retry_exc

        if not app_db_fallback_enabled():
            print(
                f"Supabase/Postgres app-data {operation_name} failed; "
                f"SQLite fallback is disabled: {exc}"
            )
            raise

        record_fallback(operation_name, exc)
        print(
            f"Supabase/Postgres app-data {operation_name} failed; "
            f"falling back to SQLite: {exc}"
        )
        return sqlite_operation()


def _without_sqlite_fallback(operation_name, postgres_operation, sqlite_operation):
    if not using_postgres():
        return sqlite_operation()

    try:
        return postgres_operation()
    except Exception as exc:
        print(
            f"Supabase/Postgres app-data {operation_name} failed; "
            f"SQLite fallback is disabled for security-sensitive identity data: {exc}"
        )
        raise


def get_storage_status():
    status = {
        "app_data": {
            "configured_backend": get_configured_app_db_backend(),
            "active_backend": get_app_db_backend(),
            "fallback_backend": "sqlite",
            "fallback_enabled": app_db_fallback_enabled(),
            "healthy": True,
            "last_fallback": get_last_fallback(),
        }
    }

    if not using_postgres():
        status["app_data"]["message"] = "SQLite app-data backend is active."

        if postgres_url_configured():
            status["app_data"].update({
                "healthy": False,
                "message": (
                    "A Supabase/Postgres URL is configured, but APP_DB_BACKEND "
                    "is set to SQLite. SQLite app-data backend is active."
                ),
                "error": (
                    "Set APP_DB_BACKEND=supabase to use Supabase/Postgres, "
                    "or remove SUPABASE_DB_URL/DATABASE_URL/POSTGRES_URL."
                ),
            })
            if get_last_fallback() is None:
                record_fallback(
                    "backend_selection",
                    status["app_data"]["error"],
                )
            status["app_data"]["last_fallback"] = get_last_fallback()

        return status

    if app_db_fallback_enabled() and postgres_circuit_is_open():
        status["app_data"].update({
            "active_backend": "sqlite",
            "healthy": False,
            "message": (
                "Supabase/Postgres is temporarily unavailable; "
                "SQLite fallback is active."
            ),
            "last_fallback": get_last_fallback(),
        })
        return status

    try:
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("select 1 as ok")
                cursor.fetchone()
    except Exception as exc:
        if _looks_like_stale_postgres_connection(exc):
            close_postgres_pool()
            try:
                with get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("select 1 as ok")
                        cursor.fetchone()
            except Exception as retry_exc:
                exc = retry_exc
            else:
                clear_fallback()
                status["app_data"]["message"] = (
                    "Supabase/Postgres app-data backend is healthy."
                )
                return status

        if app_db_fallback_enabled():
            record_fallback("health_check", exc)
            status["app_data"].update({
                "active_backend": "sqlite",
                "healthy": False,
                "message": (
                    "Supabase/Postgres is configured but unavailable; "
                    "SQLite fallback is active."
                ),
                "error": safe_error_summary(exc),
                "last_fallback": get_last_fallback(),
            })
        else:
            status["app_data"].update({
                "active_backend": "unavailable",
                "healthy": False,
                "message": (
                    "Supabase/Postgres is configured but unavailable; "
                    "SQLite fallback is disabled."
                ),
                "error": safe_error_summary(exc),
            })
        return status

    clear_fallback()
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
                        now_iso(),
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


def add_message(chat_id, role, content, reasoning_steps=None, token_usage=None):
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
                        token_usage,
                        created_at
                    )
                    values (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chat_id,
                        role,
                        content,
                        reasoning_steps,
                        token_usage,
                        now_iso(),
                    ),
                )
            conn.commit()

    return _with_fallback(
        "add_message",
        postgres_operation,
        lambda: sqlite_store.add_message(
            chat_id,
            role,
            content,
            reasoning_steps,
            token_usage,
        ),
    )


def get_messages(chat_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select role, content, reasoning_steps, token_usage, created_at
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
                "token_usage": row["token_usage"],
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
                        now_iso(),
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


def serialize_data_sources(data_sources):
    if isinstance(data_sources, str):
        data_sources = deserialize_data_sources(data_sources)

    return ",".join([
        str(item).strip()
        for item in (data_sources or ["simulator"])
        if str(item).strip()
    ]) or "simulator"


def deserialize_data_sources(value):
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def normalize_user_data_source_policy(
    allowed_data_sources=None,
    default_data_source="simulator",
):
    allowed_sources = deserialize_data_sources(
        serialize_data_sources(allowed_data_sources)
    )

    if "simulator" not in allowed_sources:
        allowed_sources.insert(0, "simulator")

    if "company" in allowed_sources:
        default_data_source = "company"

    if default_data_source not in allowed_sources:
        default_data_source = "simulator"

    return allowed_sources, default_data_source


def get_user_data_source_policy(user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select allowed_data_sources, default_data_source
                    from public.users
                    where id = %s
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()

        if not row:
            return {
                "allowed_data_sources": ["simulator"],
                "default_data_source": "simulator",
            }

        allowed_sources, default_source = normalize_user_data_source_policy(
            row["allowed_data_sources"],
            row["default_data_source"],
        )

        return {
            "allowed_data_sources": allowed_sources,
            "default_data_source": default_source,
        }

    return _without_sqlite_fallback(
        "get_user_data_source_policy",
        postgres_operation,
        lambda: sqlite_store.get_user_data_source_policy(user_id),
    )


def update_user_data_source_policy(
    user_id,
    allowed_data_sources=None,
    default_data_source="simulator",
):
    allowed_sources, default_source = normalize_user_data_source_policy(
        allowed_data_sources,
        default_data_source,
    )

    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    update public.users
                    set allowed_data_sources = %s,
                        default_data_source = %s
                    where id = %s
                    """,
                    (
                        serialize_data_sources(allowed_sources),
                        default_source,
                        user_id,
                    ),
                )
                updated = cursor.rowcount
            conn.commit()
            return updated > 0

    return _without_sqlite_fallback(
        "update_user_data_source_policy",
        postgres_operation,
        lambda: sqlite_store.update_user_data_source_policy(
            user_id,
            allowed_data_sources=allowed_sources,
            default_data_source=default_source,
        ),
    )


def upsert_telegram_identity(
    telegram_user_id,
    user_id,
    telegram_username=None,
    role="viewer",
    allowed_data_sources=None,
    is_active=True,
):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.telegram_identities (
                        telegram_user_id,
                        user_id,
                        telegram_username,
                        role,
                        allowed_data_sources,
                        is_active,
                        created_at,
                        updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (telegram_user_id) do update set
                        user_id = excluded.user_id,
                        telegram_username = excluded.telegram_username,
                        role = excluded.role,
                        allowed_data_sources = excluded.allowed_data_sources,
                        is_active = excluded.is_active,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(telegram_user_id),
                        user_id,
                        telegram_username,
                        role or "viewer",
                        serialize_data_sources(allowed_data_sources),
                        bool(is_active),
                        now_iso(),
                        now_iso(),
                    ),
                )
            conn.commit()

    return _without_sqlite_fallback(
        "upsert_telegram_identity",
        postgres_operation,
        lambda: sqlite_store.upsert_telegram_identity(
            telegram_user_id,
            user_id,
            telegram_username=telegram_username,
            role=role,
            allowed_data_sources=allowed_data_sources,
            is_active=is_active,
        ),
    )


def get_telegram_identity(telegram_user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        telegram_user_id,
                        user_id,
                        telegram_username,
                        role,
                        allowed_data_sources,
                        is_active
                    from public.telegram_identities
                    where telegram_user_id = %s
                    """,
                    (str(telegram_user_id),),
                )
                row = cursor.fetchone()

        if not row:
            return None

        return {
            "telegram_user_id": row["telegram_user_id"],
            "user_id": row["user_id"],
            "telegram_username": row["telegram_username"],
            "role": row["role"],
            "allowed_data_sources": deserialize_data_sources(
                row["allowed_data_sources"]
            ),
            "is_active": bool(row["is_active"]),
        }

    return _without_sqlite_fallback(
        "get_telegram_identity",
        postgres_operation,
        lambda: sqlite_store.get_telegram_identity(telegram_user_id),
    )


def deactivate_telegram_identity(telegram_user_id):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    update public.telegram_identities
                    set is_active = false,
                        updated_at = %s
                    where telegram_user_id = %s
                    """,
                    (now_iso(), str(telegram_user_id)),
                )
                updated = cursor.rowcount
            conn.commit()
            return updated > 0

    return _without_sqlite_fallback(
        "deactivate_telegram_identity",
        postgres_operation,
        lambda: sqlite_store.deactivate_telegram_identity(telegram_user_id),
    )


def create_telegram_link_code(code_hash, user_id, expires_at):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.telegram_link_codes (
                        code_hash,
                        user_id,
                        expires_at,
                        created_at
                    )
                    values (%s, %s, %s, %s)
                    """,
                    (code_hash, user_id, expires_at, now_iso()),
                )
            conn.commit()

    return _without_sqlite_fallback(
        "create_telegram_link_code",
        postgres_operation,
        lambda: sqlite_store.create_telegram_link_code(
            code_hash,
            user_id,
            expires_at,
        ),
    )


def get_telegram_link_code(code_hash):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select code_hash, user_id, expires_at, used_at, created_at
                    from public.telegram_link_codes
                    where code_hash = %s
                    """,
                    (code_hash,),
                )
                row = cursor.fetchone()

        if not row:
            return None

        return {
            "code_hash": row["code_hash"],
            "user_id": row["user_id"],
            "expires_at": row["expires_at"],
            "used_at": row["used_at"],
            "created_at": row["created_at"],
        }

    return _without_sqlite_fallback(
        "get_telegram_link_code",
        postgres_operation,
        lambda: sqlite_store.get_telegram_link_code(code_hash),
    )


def mark_telegram_link_code_used(code_hash):
    def postgres_operation():
        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    update public.telegram_link_codes
                    set used_at = %s
                    where code_hash = %s
                    and used_at is null
                    """,
                    (now_iso(), code_hash),
                )
                updated = cursor.rowcount
            conn.commit()
            return updated > 0

    return _without_sqlite_fallback(
        "mark_telegram_link_code_used",
        postgres_operation,
        lambda: sqlite_store.mark_telegram_link_code_used(code_hash),
    )


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
            from storage.telemetry_store import get_all_latest_devices

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
