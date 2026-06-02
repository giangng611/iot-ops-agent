import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import app as app_module  # noqa: E402
from storage.sqlite_store import create_user, verify_user  # noqa: E402


CHECK_USERNAME = "telemetry-source-checker"
CHECK_PASSWORD = "telemetry-source-checker-password"


def ensure_check_user():
    try:
        create_user(CHECK_USERNAME, CHECK_PASSWORD)
    except Exception:
        pass

    return verify_user(CHECK_USERNAME, CHECK_PASSWORD)


def main():
    user = ensure_check_user()
    client = app_module.app.test_client()

    with client.session_transaction() as session:
        session["user_id"] = user["id"]
        session["username"] = user["username"]

    for path in ["/api/devices", "/api/telemetry/sensor-001"]:
        response = client.get(path)
        payload = response.get_json()

        print(f"\nGET {path} -> {response.status_code}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        if response.status_code >= 400:
            sys.exit(1)

    print("\nTelemetry read source check completed.")


if __name__ == "__main__":
    main()
