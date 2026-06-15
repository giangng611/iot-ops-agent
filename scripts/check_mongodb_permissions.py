import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ALLOWED_RUNTIME_ACTIONS = {
    "find",
    "insert",
    "listIndexes",
    "update",
}


def evaluate_runtime_privileges(status, database_name, collection_name):
    auth_info = status.get("authInfo") or {}
    users = auth_info.get("authenticatedUsers") or []
    privileges = auth_info.get("authenticatedUserPrivileges") or []
    violations = []

    if not users:
        violations.append("MongoDB connection is not authenticated.")

    for privilege in privileges:
        resource = privilege.get("resource") or {}
        actions = set(privilege.get("actions") or [])
        unexpected_actions = sorted(actions - ALLOWED_RUNTIME_ACTIONS)
        wrong_resource = (
            resource.get("db") != database_name
            or resource.get("collection") != collection_name
        )

        if unexpected_actions:
            violations.append(
                "Unexpected MongoDB actions: "
                + ", ".join(unexpected_actions)
            )

        if actions and wrong_resource:
            violations.append(
                "MongoDB privilege targets an unexpected resource."
            )

    granted_actions = sorted({
        action
        for privilege in privileges
        for action in privilege.get("actions") or []
    })
    missing_actions = sorted(
        ALLOWED_RUNTIME_ACTIONS - set(granted_actions)
    )

    if missing_actions:
        violations.append(
            "Missing required MongoDB actions: "
            + ", ".join(missing_actions)
        )

    return {
        "authenticated": bool(users),
        "users": users,
        "granted_actions": granted_actions,
        "expected_resource": {
            "database": database_name,
            "collection": collection_name,
        },
        "secure": not violations,
        "violations": violations,
    }


def main():
    load_dotenv(ROOT / ".env")
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DB", "iot_ops_agent")
    collection_name = os.getenv(
        "MONGODB_TELEMETRY_COLLECTION",
        "telemetry",
    )

    if not uri:
        print("MONGODB_URI is required.", file=sys.stderr)
        sys.exit(1)

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)

    try:
        status = client.admin.command({
            "connectionStatus": 1,
            "showPrivileges": True,
        })
        result = evaluate_runtime_privileges(
            status,
            database_name,
            collection_name,
        )
    except Exception as exc:
        print(
            f"MongoDB permission check failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        client.close()

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    if not result["secure"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
