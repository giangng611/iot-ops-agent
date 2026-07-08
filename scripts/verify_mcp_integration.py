import os
import sys

from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv(os.path.join(ROOT_DIR, ".env"))

from services.company_mongo_proxy import (  # noqa: E402
    company_data_access_mode,
    get_company_mongo_read_proxy,
)


def main():
    print(f"company_data_access_mode={company_data_access_mode()}")

    if company_data_access_mode() != "mcp":
        print("verification_failed=COMPANY_DATA_ACCESS_MODE is not mcp")
        return 2

    try:
        with get_company_mongo_read_proxy("verify-mcp-route") as proxy:
            rows = proxy.find(
                "devicemgmt",
                "NODE",
                {},
                {"_id": 0, "rn": 1},
                limit=1,
            )
            audits = proxy.get_audit_events()
    except Exception as exc:
        print("verification_failed=mcp_proxy_call_failed")
        print(f"error_type={type(exc).__name__}")
        print(f"error={exc}")
        return 3

    mcp_events = [
        event
        for event in audits
        if isinstance(event, dict)
        and event.get("access_path") == "mcp_server"
    ]

    print(f"row_count={len(rows)}")
    print(f"audit_count={len(audits)}")
    print(f"mcp_access_path_seen={bool(mcp_events)}")

    if not mcp_events:
        print("verification_failed=no MCP audit event was produced")
        return 4

    print("verification=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
