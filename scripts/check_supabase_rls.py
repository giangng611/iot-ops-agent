import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.postgres_store import get_postgres_connection  # noqa: E402


APP_TABLES = (
    "users",
    "chats",
    "messages",
    "prompts",
    "telegram_identities",
    "telegram_link_codes",
)


def get_rls_status():
    with get_postgres_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select
                    c.relname as table_name,
                    c.relrowsecurity as rls_enabled,
                    has_table_privilege(
                        'anon',
                        'public.' || quote_ident(c.relname),
                        'SELECT, INSERT, UPDATE, DELETE'
                    ) as anon_has_data_privileges,
                    has_table_privilege(
                        'authenticated',
                        'public.' || quote_ident(c.relname),
                        'SELECT, INSERT, UPDATE, DELETE'
                    ) as authenticated_has_data_privileges
                from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = 'public'
                  and c.relkind in ('r', 'p')
                  and c.relname = any(%s)
                order by c.relname
                """,
                (list(APP_TABLES),),
            )
            return cursor.fetchall()


def main():
    try:
        rows = get_rls_status()
    except Exception as exc:
        print(f"Supabase RLS check failed: {exc}", file=sys.stderr)
        sys.exit(1)

    found_tables = {row["table_name"] for row in rows}
    missing_tables = sorted(set(APP_TABLES) - found_tables)
    insecure_tables = [
        row["table_name"]
        for row in rows
        if (
            not row["rls_enabled"]
            or row["anon_has_data_privileges"]
            or row["authenticated_has_data_privileges"]
        )
    ]

    result = {
        "tables": rows,
        "missing_tables": missing_tables,
        "secure": not missing_tables and not insecure_tables,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    if not result["secure"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
