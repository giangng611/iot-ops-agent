import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.company_mongo_proxy import get_allowed_namespaces  # noqa: E402

WRITE_OR_ADMIN_ACTIONS = {
    "createCollection",
    "createIndex",
    "dbAdmin",
    "dropCollection",
    "dropDatabase",
    "insert",
    "remove",
    "renameCollectionSameDB",
    "update",
    "userAdmin",
}


def evaluate_company_privileges(status, allowed_namespaces):
    auth_info = status.get("authInfo") or {}
    users = auth_info.get("authenticatedUsers") or []
    roles = auth_info.get("authenticatedUserRoles") or []
    privileges = auth_info.get("authenticatedUserPrivileges") or []
    allowed_databases = {
        namespace.split(".", 1)[0]
        for namespace in allowed_namespaces
    }
    violations = []
    granted_actions = set()

    if not users:
        violations.append("The company MongoDB connection is not authenticated.")

    for role in roles:
        if role.get("role") == "readAnyDatabase":
            violations.append(
                "The credential has readAnyDatabase and is broader than the "
                "application namespace allowlist."
            )

    for privilege in privileges:
        resource = privilege.get("resource") or {}
        actions = set(privilege.get("actions") or [])
        granted_actions.update(actions)
        dangerous_actions = sorted(actions & WRITE_OR_ADMIN_ACTIONS)

        if dangerous_actions:
            violations.append(
                "Write or administrative MongoDB actions were granted: "
                + ", ".join(dangerous_actions)
            )

        database_name = resource.get("db")
        collection_name = resource.get("collection")

        if database_name == "" and actions:
            violations.append(
                "A MongoDB privilege applies to every database."
            )
        elif (
            database_name
            and database_name not in allowed_databases
            and actions
        ):
            violations.append(
                f"A MongoDB privilege applies to unexpected database: "
                f"{database_name}"
            )
        elif database_name and collection_name:
            namespace = f"{database_name}.{collection_name}"

            if namespace not in allowed_namespaces and actions:
                violations.append(
                    f"A MongoDB privilege applies to unexpected namespace: "
                    f"{namespace}"
                )

    return {
        "authenticated": bool(users),
        "users": users,
        "roles": roles,
        "allowed_namespaces": sorted(allowed_namespaces),
        "granted_actions": sorted(granted_actions),
        "least_privilege": not violations,
        "violations": sorted(set(violations)),
    }


def anonymous_document_access_is_denied(uri, allowed_namespaces):
    parsed = urlsplit(uri)
    database_name, collection_name = sorted(allowed_namespaces)[0].split(
        ".",
        1,
    )
    anonymous_client = MongoClient(
        host=parsed.hostname,
        port=parsed.port or 27017,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000,
        directConnection=True,
    )

    try:
        anonymous_client[database_name][collection_name].find_one(
            {},
            {"_id": 1},
            max_time_ms=2000,
        )
    except OperationFailure:
        return True
    finally:
        anonymous_client.close()

    return False


def main():
    load_dotenv(ROOT / ".env")
    uri = os.getenv("COMPANY_MONGODB_URI")

    if not uri:
        print("COMPANY_MONGODB_URI is required.", file=sys.stderr)
        sys.exit(1)

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000,
    )

    try:
        status = client.admin.command({
            "connectionStatus": 1,
            "showPrivileges": True,
        })
        result = evaluate_company_privileges(
            status,
            get_allowed_namespaces(),
        )
        result["anonymous_document_access_denied"] = (
            anonymous_document_access_is_denied(
                uri,
                get_allowed_namespaces(),
            )
        )

        if not result["anonymous_document_access_denied"]:
            result["violations"].append(
                "The company MongoDB server permits anonymous document reads."
            )
            result["least_privilege"] = False
    except Exception as exc:
        print(
            f"Company MongoDB security check failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        client.close()

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    if not result["least_privilege"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
