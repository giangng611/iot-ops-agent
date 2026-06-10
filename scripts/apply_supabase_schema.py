import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.postgres_store import apply_schema  # noqa: E402


MIGRATIONS_DIR = ROOT / "supabase" / "migrations"


def main():
    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))

    if not migration_paths:
        print(f"No SQL migrations found in {MIGRATIONS_DIR}", file=sys.stderr)
        sys.exit(1)

    for migration_path in migration_paths:
        try:
            apply_schema(migration_path)
        except Exception as exc:
            print(
                f"Supabase/Postgres migration failed ({migration_path.name}): {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Applied migration: {migration_path}")


if __name__ == "__main__":
    main()
