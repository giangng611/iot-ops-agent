import argparse
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from database import DB_NAME  # noqa: E402
from postgres_store import (  # noqa: E402
    apply_schema,
    get_postgres_connection,
    reset_identity_sequence,
)


SCHEMA_PATH = ROOT / "supabase" / "migrations" / "20260602000100_create_app_tables.sql"
EXCLUDED_USERNAMES = {
    "security_owner",
    "security_attacker",
    "security_owner_2",
    "security_attacker_2",
    "limit_tester",
    "limit_tester_2",
    "limit-user",
    "owner",
    "other",
    "mongo-checker",
    "telemetry-source-checker",
}


def fetch_sqlite_rows(table_name):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"select * from {table_name} order by id asc")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def migrate_users(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into public.users (id, username, password_hash, created_at)
                values (%s, %s, %s, %s)
                on conflict (id) do update set
                  username = excluded.username,
                  password_hash = excluded.password_hash,
                  created_at = excluded.created_at
                """,
                (
                    row["id"],
                    row["username"],
                    row["password_hash"],
                    row["created_at"],
                ),
            )


def migrate_chats(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into public.chats (id, user_id, title, created_at, is_pinned)
                values (%s, %s, %s, %s, %s)
                on conflict (id) do update set
                  user_id = excluded.user_id,
                  title = excluded.title,
                  created_at = excluded.created_at,
                  is_pinned = excluded.is_pinned
                """,
                (
                    row["id"],
                    row.get("user_id"),
                    row["title"],
                    row["created_at"],
                    bool(row.get("is_pinned", 0)),
                ),
            )


def migrate_messages(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into public.messages (
                  id,
                  chat_id,
                  role,
                  content,
                  reasoning_steps,
                  created_at
                )
                values (%s, %s, %s, %s, %s, %s)
                on conflict (id) do update set
                  chat_id = excluded.chat_id,
                  role = excluded.role,
                  content = excluded.content,
                  reasoning_steps = excluded.reasoning_steps,
                  created_at = excluded.created_at
                """,
                (
                    row["id"],
                    row["chat_id"],
                    row["role"],
                    row["content"],
                    row.get("reasoning_steps"),
                    row["created_at"],
                ),
            )


def migrate_prompts(conn, rows):
    with conn.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into public.prompts (
                  id,
                  user_id,
                  title,
                  command,
                  category,
                  is_default,
                  created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (id) do update set
                  user_id = excluded.user_id,
                  title = excluded.title,
                  command = excluded.command,
                  category = excluded.category,
                  is_default = excluded.is_default,
                  created_at = excluded.created_at
                """,
                (
                    row["id"],
                    row["user_id"],
                    row["title"],
                    row["command"],
                    row["category"],
                    bool(row.get("is_default", 0)),
                    row.get("created_at"),
                ),
            )


def count_postgres_rows(conn, table_name):
    with conn.cursor() as cursor:
        cursor.execute(f"select count(*) as count from public.{table_name}")
        return cursor.fetchone()["count"]


def main():
    parser = argparse.ArgumentParser(
        description="Migrate SQLite app data to Supabase/Postgres."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to Supabase/Postgres. Default is dry run.",
    )
    args = parser.parse_args()

    tables = ["users", "chats", "messages", "prompts"]
    sqlite_rows = {
        table_name: fetch_sqlite_rows(table_name)
        for table_name in tables
    }

    excluded_user_ids = {
        row["id"]
        for row in sqlite_rows["users"]
        if row["username"] in EXCLUDED_USERNAMES
    }
    sqlite_rows["users"] = [
        row for row in sqlite_rows["users"]
        if row["id"] not in excluded_user_ids
    ]
    sqlite_rows["chats"] = [
        row for row in sqlite_rows["chats"]
        if row.get("user_id") not in excluded_user_ids
    ]
    included_chat_ids = {row["id"] for row in sqlite_rows["chats"]}
    sqlite_rows["messages"] = [
        row for row in sqlite_rows["messages"]
        if row["chat_id"] in included_chat_ids
    ]
    sqlite_rows["prompts"] = [
        row for row in sqlite_rows["prompts"]
        if row["user_id"] not in excluded_user_ids
    ]

    print("SQLite source counts:")
    for table_name in tables:
        print(f"- {table_name}: {len(sqlite_rows[table_name])}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to migrate.")
        return

    apply_schema(SCHEMA_PATH)

    with get_postgres_connection() as conn:
        migrate_users(conn, sqlite_rows["users"])
        migrate_chats(conn, sqlite_rows["chats"])
        migrate_messages(conn, sqlite_rows["messages"])
        migrate_prompts(conn, sqlite_rows["prompts"])

        for table_name in tables:
            reset_identity_sequence(conn, table_name)

        conn.commit()

        print("\nSupabase/Postgres target counts:")
        for table_name in tables:
            print(f"- {table_name}: {count_postgres_rows(conn, table_name)}")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
