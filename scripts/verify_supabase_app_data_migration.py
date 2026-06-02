import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from postgres_store import get_postgres_connection  # noqa: E402
from scripts.migrate_sqlite_app_data_to_supabase import (  # noqa: E402
    EXCLUDED_USERNAMES,
    load_filtered_sqlite_app_rows,
)


def count_postgres_rows(conn, table_name):
    with conn.cursor() as cursor:
        cursor.execute(f"select count(*) as count from public.{table_name}")
        return cursor.fetchone()["count"]


def count_excluded_users(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            select count(*) as count
            from public.users
            where username = any(%s)
            """,
            (list(EXCLUDED_USERNAMES),),
        )
        return cursor.fetchone()["count"]


def count_orphans(conn):
    checks = {}

    with conn.cursor() as cursor:
        cursor.execute(
            """
            select count(*) as count
            from public.chats c
            left join public.users u on u.id = c.user_id
            where c.user_id is not null
            and u.id is null
            """
        )
        checks["chats_without_users"] = cursor.fetchone()["count"]

        cursor.execute(
            """
            select count(*) as count
            from public.messages m
            left join public.chats c on c.id = m.chat_id
            where c.id is null
            """
        )
        checks["messages_without_chats"] = cursor.fetchone()["count"]

        cursor.execute(
            """
            select count(*) as count
            from public.prompts p
            left join public.users u on u.id = p.user_id
            where u.id is null
            """
        )
        checks["prompts_without_users"] = cursor.fetchone()["count"]

    return checks


def count_missing_migrated_ids(conn, table_name, source_ids):
    if not source_ids:
        return 0

    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            select count(*) as count
            from unnest(%s::int[]) as source(id)
            left join public.{table_name} target on target.id = source.id
            where target.id is null
            """,
            (list(source_ids),),
        )
        return cursor.fetchone()["count"]


def main():
    tables = ["users", "chats", "messages", "prompts"]
    sqlite_rows = load_filtered_sqlite_app_rows()
    sqlite_counts = {
        table_name: len(sqlite_rows[table_name])
        for table_name in tables
    }

    with get_postgres_connection() as conn:
        postgres_counts = {
            table_name: count_postgres_rows(conn, table_name)
            for table_name in tables
        }
        missing_migrated_ids = {
            table_name: count_missing_migrated_ids(
                conn,
                table_name,
                {row["id"] for row in sqlite_rows[table_name]},
            )
            for table_name in tables
        }
        excluded_user_count = count_excluded_users(conn)
        orphan_counts = count_orphans(conn)

    target_has_at_least_source = {
        table_name: postgres_counts[table_name] >= sqlite_counts[table_name]
        for table_name in tables
    }
    passed = (
        all(target_has_at_least_source.values())
        and all(count == 0 for count in missing_migrated_ids.values())
        and excluded_user_count == 0
        and all(count == 0 for count in orphan_counts.values())
    )

    result = {
        "passed": passed,
        "sqlite_source_counts": sqlite_counts,
        "supabase_target_counts": postgres_counts,
        "target_has_at_least_source": target_has_at_least_source,
        "missing_migrated_ids": missing_migrated_ids,
        "excluded_user_count": excluded_user_count,
        "orphan_counts": orphan_counts,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
