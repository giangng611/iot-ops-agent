import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.postgres_store import postgres_url_configured  # noqa: E402
from storage.relational_store import (  # noqa: E402
    deactivate_telegram_identity,
    get_app_db_backend,
    get_configured_app_db_backend,
    get_telegram_identity,
    init_db,
)


def main():
    parser = argparse.ArgumentParser(
        description="Deactivate a Telegram link for IoT Ops Agent."
    )
    parser.add_argument("--telegram-user-id", required=True)
    parser.add_argument(
        "--allow-sqlite-fallback",
        action="store_true",
        help=(
            "Allow fallback to local SQLite if Supabase/Postgres is configured "
            "but unavailable."
        ),
    )
    args = parser.parse_args()

    if (
        postgres_url_configured()
        and not args.allow_sqlite_fallback
        and "APP_DB_FALLBACK_ENABLED" not in os.environ
    ):
        os.environ["APP_DB_FALLBACK_ENABLED"] = "false"

    init_db()
    print(
        "Using app DB backend: "
        f"{get_app_db_backend()} "
        f"(configured: {get_configured_app_db_backend()})"
    )

    identity = get_telegram_identity(args.telegram_user_id)

    if not identity:
        print(f"Telegram identity not found: {args.telegram_user_id}")
        return 1

    if not identity.get("is_active"):
        print(f"Telegram identity is already inactive: {args.telegram_user_id}")
        return 0

    if not deactivate_telegram_identity(args.telegram_user_id):
        print(f"Telegram identity not found: {args.telegram_user_id}")
        return 1

    print(f"Deactivated Telegram identity: {args.telegram_user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
