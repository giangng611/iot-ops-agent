import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.postgres_store import get_postgres_connection  # noqa: E402
from storage.mysql_store import mysql_connection  # noqa: E402


APP_TABLES = [
    "users",
    "chats",
    "messages",
    "prompts",
    "telegram_identities",
    "telegram_link_codes",
]


def postgres_ids(table_name):
    with get_postgres_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"select id from public.{table_name} order by id asc")
            return {row["id"] for row in cursor.fetchall()}


def mysql_ids(conn, table_name):
    with conn.cursor() as cursor:
        cursor.execute(f"select id from `{table_name}` order by id asc")
        return {row["id"] for row in cursor.fetchall()}


def main():
    ok = True

    with mysql_connection() as conn:
        print("App-data migration verification:")

        for table_name in APP_TABLES:
            source_ids = postgres_ids(table_name)
            target_ids = mysql_ids(conn, table_name)
            missing = source_ids - target_ids
            extra = target_ids - source_ids
            table_ok = not missing
            ok = ok and table_ok

            print(
                f"- {table_name}: postgres={len(source_ids)} "
                f"mysql={len(target_ids)} missing={len(missing)} extra={len(extra)}"
            )

            if missing:
                preview = sorted(missing)[:10]
                print(f"  missing ids preview: {preview}")

    if not ok:
        raise SystemExit(1)

    print("\nVerification passed: all Supabase/Postgres IDs exist in MySQL.")


if __name__ == "__main__":
    main()
