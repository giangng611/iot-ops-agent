import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from postgres_store import apply_schema  # noqa: E402


SCHEMA_PATH = ROOT / "supabase" / "migrations" / "20260602000100_create_app_tables.sql"


def main():
    try:
        apply_schema(SCHEMA_PATH)
    except Exception as exc:
        print(f"Supabase/Postgres schema apply failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Applied schema: {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
