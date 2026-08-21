import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.mysql_store import apply_schema, check_connection  # noqa: E402


SCHEMA_PATH = ROOT / "mysql" / "migrations" / "001_create_app_tables.sql"


def main():
    print(f"Applying MySQL schema: {SCHEMA_PATH}")
    apply_schema(SCHEMA_PATH)
    info = check_connection()
    print(f"MySQL schema is ready on database: {info.get('database_name')}")


if __name__ == "__main__":
    main()
