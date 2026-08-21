import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.postgres_store import get_postgres_connection  # noqa: E402
from storage.mysql_store import (  # noqa: E402
    apply_schema,
    mysql_connection,
    reset_auto_increment,
)


SCHEMA_PATH = ROOT / "mysql" / "migrations" / "001_create_app_tables.sql"
APP_TABLES = [
    "users",
    "chats",
    "messages",
    "prompts",
    "telegram_identities",
    "telegram_link_codes",
]


def fetch_postgres_rows(table_name):
    with get_postgres_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"select * from public.{table_name} order by id asc")
            return [dict(row) for row in cursor.fetchall()]


def count_mysql_rows(conn, table_name):
    with conn.cursor() as cursor:
        cursor.execute(f"select count(*) as count from `{table_name}`")
        return cursor.fetchone()["count"]


def bool_to_int(value):
    if isinstance(value, str):
        return 1 if value.strip().lower() in {"1", "true", "t", "yes", "on"} else 0

    return 1 if bool(value) else 0


def migrate_users(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into users (
                  id,
                  username,
                  password_hash,
                  created_at,
                  allowed_data_sources,
                  default_data_source
                )
                values (%s, %s, %s, %s, %s, %s)
                on duplicate key update
                  username = values(username),
                  password_hash = values(password_hash),
                  created_at = values(created_at),
                  allowed_data_sources = values(allowed_data_sources),
                  default_data_source = values(default_data_source)
                """,
                (
                    row["id"],
                    row["username"],
                    row["password_hash"],
                    row["created_at"],
                    row.get("allowed_data_sources") or "simulator",
                    row.get("default_data_source") or "simulator",
                ),
            )


def migrate_chats(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into chats (id, user_id, title, created_at, is_pinned)
                values (%s, %s, %s, %s, %s)
                on duplicate key update
                  user_id = values(user_id),
                  title = values(title),
                  created_at = values(created_at),
                  is_pinned = values(is_pinned)
                """,
                (
                    row["id"],
                    row.get("user_id"),
                    row["title"],
                    row["created_at"],
                    bool_to_int(row.get("is_pinned")),
                ),
            )


def migrate_messages(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into messages (
                  id,
                  chat_id,
                  role,
                  content,
                  reasoning_steps,
                  token_usage,
                  created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s)
                on duplicate key update
                  chat_id = values(chat_id),
                  role = values(role),
                  content = values(content),
                  reasoning_steps = values(reasoning_steps),
                  token_usage = values(token_usage),
                  created_at = values(created_at)
                """,
                (
                    row["id"],
                    row["chat_id"],
                    row["role"],
                    row["content"],
                    row.get("reasoning_steps"),
                    row.get("token_usage"),
                    row["created_at"],
                ),
            )


def migrate_prompts(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into prompts (
                  id,
                  user_id,
                  title,
                  command,
                  category,
                  is_default,
                  created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s)
                on duplicate key update
                  user_id = values(user_id),
                  title = values(title),
                  command = values(command),
                  category = values(category),
                  is_default = values(is_default),
                  created_at = values(created_at)
                """,
                (
                    row["id"],
                    row["user_id"],
                    row["title"],
                    row["command"],
                    row["category"],
                    bool_to_int(row.get("is_default")),
                    row.get("created_at"),
                ),
            )


def migrate_telegram_identities(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into telegram_identities (
                  id,
                  telegram_user_id,
                  user_id,
                  telegram_username,
                  role,
                  allowed_data_sources,
                  is_active,
                  created_at,
                  updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on duplicate key update
                  telegram_user_id = values(telegram_user_id),
                  user_id = values(user_id),
                  telegram_username = values(telegram_username),
                  role = values(role),
                  allowed_data_sources = values(allowed_data_sources),
                  is_active = values(is_active),
                  created_at = values(created_at),
                  updated_at = values(updated_at)
                """,
                (
                    row["id"],
                    row["telegram_user_id"],
                    row["user_id"],
                    row.get("telegram_username"),
                    row.get("role") or "viewer",
                    row.get("allowed_data_sources") or "simulator",
                    bool_to_int(row.get("is_active")),
                    row["created_at"],
                    row["updated_at"],
                ),
            )


def migrate_telegram_link_codes(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into telegram_link_codes (
                  id,
                  code_hash,
                  user_id,
                  expires_at,
                  used_at,
                  created_at
                )
                values (%s, %s, %s, %s, %s, %s)
                on duplicate key update
                  code_hash = values(code_hash),
                  user_id = values(user_id),
                  expires_at = values(expires_at),
                  used_at = values(used_at),
                  created_at = values(created_at)
                """,
                (
                    row["id"],
                    row["code_hash"],
                    row["user_id"],
                    row["expires_at"],
                    row.get("used_at"),
                    row["created_at"],
                ),
            )


MIGRATORS = {
    "users": migrate_users,
    "chats": migrate_chats,
    "messages": migrate_messages,
    "prompts": migrate_prompts,
    "telegram_identities": migrate_telegram_identities,
    "telegram_link_codes": migrate_telegram_link_codes,
}


def main():
    parser = argparse.ArgumentParser(
        description="Migrate app-owned data from Supabase/Postgres to MySQL."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to MySQL. Default is a read-only dry run.",
    )
    args = parser.parse_args()

    postgres_rows = {
        table_name: fetch_postgres_rows(table_name)
        for table_name in APP_TABLES
    }

    print("Supabase/Postgres source counts:")
    for table_name in APP_TABLES:
        print(f"- {table_name}: {len(postgres_rows[table_name])}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write to MySQL.")
        return

    apply_schema(SCHEMA_PATH)

    with mysql_connection() as conn:
        for table_name in APP_TABLES:
            MIGRATORS[table_name](conn, postgres_rows[table_name])

        for table_name in APP_TABLES:
            reset_auto_increment(conn, table_name)

        conn.commit()

        print("\nMySQL target counts:")
        for table_name in APP_TABLES:
            print(f"- {table_name}: {count_mysql_rows(conn, table_name)}")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
