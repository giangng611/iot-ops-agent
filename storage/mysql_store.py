import atexit
import json
import os
from contextlib import contextmanager
from urllib.parse import parse_qs, unquote, urlparse

from werkzeug.security import check_password_hash, generate_password_hash

from services.time_service import now, now_iso, parse_timestamp

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    pymysql = None
    DictCursor = None


APP_TABLES = {
    "users",
    "chats",
    "messages",
    "prompts",
    "telegram_identities",
    "telegram_link_codes",
}


def get_mysql_url():
    return (
        os.getenv("MYSQL_DB_URL")
        or os.getenv("MYSQL_URL")
        or os.getenv("APP_MYSQL_URL")
    )


def mysql_url_configured():
    return bool(get_mysql_url() or os.getenv("MYSQL_HOST"))


def mysql_enabled():
    configured_backend = os.getenv("APP_DB_BACKEND")
    return configured_backend is not None and configured_backend.lower() == "mysql"


def get_mysql_runtime_timeouts():
    return {
        "connect_timeout": int(os.getenv("MYSQL_CONNECT_TIMEOUT_SECONDS", "5")),
        "read_timeout": int(os.getenv("MYSQL_READ_TIMEOUT_SECONDS", "5")),
        "write_timeout": int(os.getenv("MYSQL_WRITE_TIMEOUT_SECONDS", "5")),
    }


def _connection_kwargs_from_url(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise RuntimeError(
            "MYSQL_DB_URL must use mysql:// or mysql+pymysql://."
        )

    database = parsed.path.lstrip("/")
    if not database:
        raise RuntimeError("MYSQL_DB_URL must include a database name.")

    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(database),
        "charset": query.get("charset", ["utf8mb4"])[0],
    }


def get_mysql_connection_kwargs():
    if get_mysql_url():
        kwargs = _connection_kwargs_from_url(get_mysql_url())
    else:
        kwargs = {
            "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "port": int(os.getenv("MYSQL_PORT", "3306")),
            "user": os.getenv("MYSQL_USER", ""),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", ""),
            "charset": os.getenv("MYSQL_CHARSET", "utf8mb4"),
        }

    timeouts = get_mysql_runtime_timeouts()
    kwargs.update({
        "cursorclass": DictCursor,
        "autocommit": False,
        "connect_timeout": timeouts["connect_timeout"],
        "read_timeout": timeouts["read_timeout"],
        "write_timeout": timeouts["write_timeout"],
    })
    return kwargs


def get_mysql_connection():
    if pymysql is None:
        raise RuntimeError(
            "PyMySQL is not installed. Run `pip install -r requirements.txt` "
            "before enabling MySQL app data."
        )

    kwargs = get_mysql_connection_kwargs()
    if not kwargs.get("database"):
        raise RuntimeError(
            "MYSQL_DB_URL or MYSQL_DATABASE is required for MySQL app data."
        )

    return pymysql.connect(**kwargs)


def close_mysql_pool():
    # PyMySQL connections are opened per operation for now. This hook mirrors
    # the Postgres store API so callers can clean up without backend checks.
    return None


atexit.register(close_mysql_pool)


@contextmanager
def mysql_connection():
    conn = get_mysql_connection()
    try:
        yield conn
    finally:
        conn.close()


def apply_schema(schema_path):
    with open(schema_path, "r", encoding="utf-8") as file:
        schema_sql = file.read()

    statements = [
        statement.strip()
        for statement in schema_sql.split(";")
        if statement.strip()
    ]

    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        conn.commit()


def check_connection():
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select database() as database_name, version() as version"
            )
            return cursor.fetchone()


def reset_auto_increment(conn, table_name):
    if table_name not in APP_TABLES:
        raise ValueError(f"Unsupported app-data table: {table_name}")

    with conn.cursor() as cursor:
        cursor.execute(f"select coalesce(max(id), 0) + 1 as next_id from `{table_name}`")
        next_id = cursor.fetchone()["next_id"]
        cursor.execute(f"alter table `{table_name}` auto_increment = %s", (next_id,))


def _as_bool(value):
    return bool(int(value)) if value is not None else False


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


def create_chat(user_id, title):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                insert into chats (user_id, title, created_at)
                values (%s, %s, %s)
                """,
                (user_id, title, now_iso()),
            )
            chat_id = cursor.lastrowid
        conn.commit()
        return chat_id


def get_chats(user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select id, title, created_at, is_pinned
                from chats
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
            "is_pinned": _as_bool(row["is_pinned"]),
        }
        for row in rows
    ]


def chat_belongs_to_user(chat_id, user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select 1
                from chats
                where id = %s
                and user_id = %s
                limit 1
                """,
                (chat_id, user_id),
            )
            return cursor.fetchone() is not None


def add_message(chat_id, role, content, reasoning_steps=None, token_usage=None):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                insert into messages (
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


def get_messages(chat_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select role, content, reasoning_steps, token_usage, created_at
                from messages
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


def create_user(username, password):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                insert into users (username, password_hash, created_at)
                values (%s, %s, %s)
                """,
                (username, generate_password_hash(password), now_iso()),
            )
        conn.commit()


def get_user_by_username(username):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select id, username, password_hash
                from users
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


def verify_user(username, password):
    user = get_user_by_username(username)

    if not user:
        return None

    if not check_password_hash(user["password_hash"], password):
        return None

    return user


def get_user_data_source_policy(user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select allowed_data_sources, default_data_source
                from users
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


def update_user_data_source_policy(
    user_id,
    allowed_data_sources=None,
    default_data_source="simulator",
):
    allowed_sources, default_source = normalize_user_data_source_policy(
        allowed_data_sources,
        default_data_source,
    )

    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update users
                set allowed_data_sources = %s,
                    default_data_source = %s
                where id = %s
                """,
                (serialize_data_sources(allowed_sources), default_source, user_id),
            )
            updated = cursor.rowcount
        conn.commit()
        return updated > 0


def upsert_telegram_identity(
    telegram_user_id,
    user_id,
    telegram_username=None,
    role="viewer",
    allowed_data_sources=None,
    is_active=True,
):
    timestamp = now_iso()
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                insert into telegram_identities (
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
                on duplicate key update
                    user_id = values(user_id),
                    telegram_username = values(telegram_username),
                    role = values(role),
                    allowed_data_sources = values(allowed_data_sources),
                    is_active = values(is_active),
                    updated_at = values(updated_at)
                """,
                (
                    str(telegram_user_id),
                    user_id,
                    telegram_username,
                    role or "viewer",
                    serialize_data_sources(allowed_data_sources),
                    1 if is_active else 0,
                    timestamp,
                    timestamp,
                ),
            )
        conn.commit()


def get_telegram_identity(telegram_user_id):
    with mysql_connection() as conn:
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
                from telegram_identities
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
        "is_active": _as_bool(row["is_active"]),
    }


def deactivate_telegram_identity(telegram_user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update telegram_identities
                set is_active = 0,
                    updated_at = %s
                where telegram_user_id = %s
                """,
                (now_iso(), str(telegram_user_id)),
            )
            updated = cursor.rowcount
        conn.commit()
        return updated > 0


def create_telegram_link_code(code_hash, user_id, expires_at):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                insert into telegram_link_codes (
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


def get_telegram_link_code(code_hash):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select code_hash, user_id, expires_at, used_at, created_at
                from telegram_link_codes
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


def mark_telegram_link_code_used(code_hash):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update telegram_link_codes
                set used_at = %s
                where code_hash = %s
                and used_at is null
                """,
                (now_iso(), code_hash),
            )
            updated = cursor.rowcount
        conn.commit()
        return updated > 0


def delete_chat(chat_id, user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                delete from chats
                where id = %s
                and user_id = %s
                """,
                (chat_id, user_id),
            )
            deleted = cursor.rowcount
        conn.commit()
        return deleted > 0


def toggle_pin_chat(chat_id, user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select is_pinned
                from chats
                where id = %s
                and user_id = %s
                """,
                (chat_id, user_id),
            )
            row = cursor.fetchone()

            if not row:
                return None

            new_value = 0 if _as_bool(row["is_pinned"]) else 1
            cursor.execute(
                """
                update chats
                set is_pinned = %s
                where id = %s
                and user_id = %s
                """,
                (new_value, chat_id, user_id),
            )
        conn.commit()
        return bool(new_value)


def change_user_password(user_id, current_password, new_password):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select password_hash
                from users
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
                update users
                set password_hash = %s
                where id = %s
                """,
                (generate_password_hash(new_password), user_id),
            )
        conn.commit()
        return True, "Password updated successfully"


def get_prompts(user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select id, title, command, category, is_default
                from prompts
                where user_id = %s or is_default = 1
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
            "is_default": _as_bool(row["is_default"]),
        }
        for row in rows
    ]


def create_prompt(user_id, title, command, category):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                insert into prompts (
                    user_id,
                    title,
                    command,
                    category,
                    is_default,
                    created_at
                )
                values (%s, %s, %s, %s, 0, %s)
                """,
                (user_id, title, command, category, now_iso()),
            )
            prompt_id = cursor.lastrowid
        conn.commit()
        return prompt_id


def update_prompt(prompt_id, user_id, title, command, category):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update prompts
                set title = %s,
                    command = %s,
                    category = %s
                where id = %s
                and user_id = %s
                and is_default = 0
                """,
                (title, command, category, prompt_id, user_id),
            )
            updated = cursor.rowcount
        conn.commit()
        return updated > 0


def delete_prompt(prompt_id, user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                delete from prompts
                where id = %s
                and user_id = %s
                and is_default = 0
                """,
                (prompt_id, user_id),
            )
            deleted = cursor.rowcount
        conn.commit()
        return deleted > 0


def update_username(user_id, new_username):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update users
                set username = %s
                where id = %s
                """,
                (new_username, user_id),
            )
            updated = cursor.rowcount
        conn.commit()
        return updated > 0


def delete_user_account(user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                delete from prompts
                where user_id = %s
                and is_default = 0
                """,
                (user_id,),
            )
            cursor.execute(
                """
                delete from users
                where id = %s
                """,
                (user_id,),
            )
            deleted = cursor.rowcount
        conn.commit()
        return deleted > 0


def get_user_usage_stats(user_id):
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select count(*) as count from chats where user_id = %s",
                (user_id,),
            )
            chat_count = cursor.fetchone()["count"]

            cursor.execute(
                """
                select count(*) as count
                from messages
                where chat_id in (
                    select id from chats where user_id = %s
                )
                """,
                (user_id,),
            )
            message_count = cursor.fetchone()["count"]

            cursor.execute(
                """
                select token_usage, created_at
                from messages
                where token_usage is not null
                and chat_id in (
                    select id from chats where user_id = %s
                )
                """,
                (user_id,),
            )
            today = now().date()
            today_token_total = 0

            for row in cursor.fetchall():
                try:
                    created_at = parse_timestamp(str(row["created_at"]))
                except Exception:
                    continue

                if created_at.date() != today:
                    continue

                token_usage = row["token_usage"]

                if isinstance(token_usage, str):
                    try:
                        token_usage = json.loads(token_usage)
                    except ValueError:
                        continue

                if isinstance(token_usage, dict):
                    today_token_total += int(
                        token_usage.get("total_tokens") or 0
                    )

            cursor.execute(
                """
                select count(*) as count
                from prompts
                where user_id = %s
                and is_default = 0
                """,
                (user_id,),
            )
            custom_prompt_count = cursor.fetchone()["count"]

    try:
        from storage.telemetry_store import get_all_latest_devices

        device_count = len(get_all_latest_devices())
    except Exception:
        device_count = 0

    return {
        "chat_count": chat_count,
        "message_count": message_count,
        "custom_prompt_count": custom_prompt_count,
        "device_count": device_count,
        "today_token_total": today_token_total,
    }
