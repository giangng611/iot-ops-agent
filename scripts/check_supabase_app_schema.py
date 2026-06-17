import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.postgres_store import get_postgres_connection  # noqa: E402


REQUIRED_COLUMNS = {
    "users": {
        "allowed_data_sources",
        "default_data_source",
    },
    "telegram_identities": {
        "telegram_user_id",
        "user_id",
        "allowed_data_sources",
        "is_active",
    },
    "telegram_link_codes": {
        "code_hash",
        "user_id",
        "expires_at",
        "used_at",
    },
}


def fetch_columns():
    with get_postgres_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select table_name, column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = any(%s)
                order by table_name, ordinal_position
                """,
                (list(REQUIRED_COLUMNS),),
            )
            rows = cursor.fetchall()

    columns_by_table = {table_name: set() for table_name in REQUIRED_COLUMNS}

    for row in rows:
        columns_by_table[row["table_name"]].add(row["column_name"])

    return columns_by_table


def main():
    try:
        columns_by_table = fetch_columns()
    except Exception as exc:
        print(f"Supabase app schema check failed: {exc}", file=sys.stderr)
        return 1

    missing = {
        table_name: sorted(required_columns - columns_by_table[table_name])
        for table_name, required_columns in REQUIRED_COLUMNS.items()
    }
    missing = {
        table_name: columns
        for table_name, columns in missing.items()
        if columns
    }

    result = {
        "ok": not missing,
        "missing": missing,
        "checked_tables": sorted(REQUIRED_COLUMNS),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
