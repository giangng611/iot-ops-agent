import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import app as app_module  # noqa: E402
from database import create_user, verify_user  # noqa: E402


CHECK_USERNAME = "mongo-checker"
CHECK_PASSWORD = "mongo-checker-password"


def ensure_check_user():
    try:
        create_user(CHECK_USERNAME, CHECK_PASSWORD)
    except Exception:
        pass

    return verify_user(CHECK_USERNAME, CHECK_PASSWORD)


def main():
    parser = argparse.ArgumentParser(
        description="Check MongoDB telemetry read APIs through Flask routes."
    )
    parser.add_argument(
        "--device-id",
        default="sensor-001",
        help="Device ID to use for MongoDB telemetry history check.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of latest records/history rows to request.",
    )
    args = parser.parse_args()

    user = ensure_check_user()
    client = app_module.app.test_client()

    with client.session_transaction() as session:
        session["user_id"] = user["id"]
        session["username"] = user["username"]

    paths = [
        f"/api/mongo/telemetry/health?limit={args.limit}",
        "/api/mongo/devices",
        f"/api/mongo/telemetry/{args.device_id}?limit={args.limit}",
    ]

    for path in paths:
        response = client.get(path)
        print(f"\nGET {path} -> {response.status_code}")
        print(json.dumps(response.get_json(), indent=2, ensure_ascii=False))

        if response.status_code >= 400:
            sys.exit(1)


if __name__ == "__main__":
    main()
