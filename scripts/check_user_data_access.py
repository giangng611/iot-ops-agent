import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.relational_store import (  # noqa: E402
    get_telegram_identity,
    get_user_by_username,
    get_user_data_source_policy,
)


def main():
    parser = argparse.ArgumentParser(
        description="Check web and Telegram data-source access for a user."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--telegram-user-id")
    args = parser.parse_args()

    user = get_user_by_username(args.username)

    if not user:
        print(f"User not found: {args.username}", file=sys.stderr)
        return 1

    identity = (
        get_telegram_identity(args.telegram_user_id)
        if args.telegram_user_id
        else None
    )
    user_policy = get_user_data_source_policy(user["id"])
    result = {
        "username": user["username"],
        "user_id": user["id"],
        "web_policy": user_policy,
        "telegram_identity": identity,
        "web_company_enabled": (
            "company" in user_policy.get("allowed_data_sources", [])
        ),
        "telegram_company_enabled": (
            identity is not None
            and identity.get("is_active")
            and "company" in identity.get("allowed_data_sources", [])
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
