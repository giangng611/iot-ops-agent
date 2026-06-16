import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.relational_store import (  # noqa: E402
    get_user_by_username,
    init_db,
    upsert_telegram_identity,
)


def parse_data_sources(value):
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Map a Telegram user ID to an IoT Ops Agent user."
    )
    parser.add_argument("--telegram-user-id", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--telegram-username")
    parser.add_argument("--role", default="operator")
    parser.add_argument("--data-sources", default="simulator")
    parser.add_argument("--inactive", action="store_true")
    args = parser.parse_args()

    init_db()
    user = get_user_by_username(args.username)

    if not user:
        print(f"User not found: {args.username}", file=sys.stderr)
        return 1

    upsert_telegram_identity(
        args.telegram_user_id,
        user["id"],
        telegram_username=args.telegram_username,
        role=args.role,
        allowed_data_sources=parse_data_sources(args.data_sources),
        is_active=not args.inactive,
    )
    print(
        "Mapped Telegram user "
        f"{args.telegram_user_id} to {args.username} "
        f"with data sources: {args.data_sources}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
