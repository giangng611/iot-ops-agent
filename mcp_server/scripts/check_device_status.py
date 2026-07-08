"""Automate runbook scenario 7 (kiem tra thiet bi X) against the live
mcp_server/:

  Step 1: input -- device_id (required) + optional request_id,
          application_domain, time_range (--minutes), resource_name,
          error_message (printed for context; resource_name narrows which
          extra resource-specific note is added in Step 5, the others are
          informational only -- this script does not yet correlate them
          against logs/queries beyond device_id).
  Step 2: grep adapter logs (iot-http-api, iot-mqtt-client-adapter).
  Step 3: check IDENTITY, AE, SUB, CNT, CIN, URI_MAPPER in Mongo (same
          queries as scenario 5/6 -- only namespaces already on the
          allowlist are queried; $regex lookups from the runbook are
          intentionally NOT run, see services/company_mongo_proxy.py
          BLOCKED_QUERY_OPERATORS).
  Step 4: (not automated) if the collection/field mapping for a resource is
          unclear, a human/agent should read the relevant service source
          code -- this script only prints a reminder, it does not grep the
          codebase itself.
  Step 5: prints the conclusion in the exact template the runbook asks for:
            Ket luan:
            - Thiet bi da/chua len he thong.
            - Cac resource da ton tai: ...
            - Cac resource con thieu: ...
            - Log loi phat hien: ...
            - Nguyen nhan kha nghi: ...
            - De xuat xu ly tiep theo: ...

This only *reads* through mcp_server/ tools (same guardrails/auth as any
other caller).

Usage:
  python mcp_server/scripts/check_device_status.py <device_id> [options]

Options:
  --request-id ID
  --application-domain TEXT
  --resource-name {IDENTITY,AE,SUB,CNT,CIN,URI_MAPPER}
  --error-message TEXT
  --minutes N              how far back to search Loki logs (default 60)
  --adapter-services a,b   comma list of adapter services to grep (default:
                            iot-http-api,iot-mqtt-client-adapter)

Env vars (same as manual_test_client.py): MCP_SERVER_URL, MCP_TEST_BEARER_KEY
"""
import argparse
import asyncio

from _debug_common import grep_services, mcp_session, mongo_find, print_header, split_csv, time_window

RESOURCE_QUERIES = {
    "IDENTITY": ("authorization", "IDENTITY", lambda device_id: {"_id": device_id}),
    "AE": ("subNNotif", "AE", lambda device_id: {"_id": device_id}),
    "SUB": ("subNNotif", "SUB", lambda device_id: {"cr": device_id}),
    "CNT": ("datamgmt", "CNT", lambda device_id: {"pi": device_id}),
    "CIN": ("datamgmt", "CIN", lambda device_id: {"cr": device_id}),
    "URI_MAPPER": ("orchestration", "URI_MAPPER", lambda device_id: {"nhuri": device_id}),
}


async def run(device_id, request_id, application_domain, resource_name, error_message, minutes, adapter_services):
    start, end = time_window(minutes)

    async with mcp_session() as session:
        print_header("Step 1: input")
        print(f"device_id           = {device_id}")
        print(f"request_id          = {request_id or '(khong co)'}")
        print(f"application_domain  = {application_domain or '(khong co)'}")
        print(f"resource_name       = {resource_name or '(khong co)'}")
        print(f"error_message       = {error_message or '(khong co)'}")
        print(f"time_range          = last {minutes}m")

        print_header(f"Step 2: adapter logs for device_id={device_id} (last {minutes}m)")
        adapter_hits = await grep_services(session, adapter_services, device_id, start, end)
        any_adapter_log = any(adapter_hits.values())
        adapter_log_lines = [
            line for matches in adapter_hits.values() for _ts_ms, line, _labels in matches
        ]
        error_keywords = ("error", "exception", "fail", "timeout", "refused", "denied")
        error_log_lines = [
            line for line in adapter_log_lines
            if any(keyword in line.lower() for keyword in error_keywords)
        ]

        print_header("Step 3: database resources")
        resource_states = {}

        for name, (database, collection, build_query) in RESOURCE_QUERIES.items():
            extra_kwargs = {"sort": ("ct", -1)} if name == "CIN" else {}
            state, _docs = await mongo_find(
                session, name, database, collection, build_query(device_id), **extra_kwargs,
            )
            resource_states[name] = state

        print_header("Step 4: doc source code (khong tu dong hoa)")
        print(
            "Neu chua ro ten collection/field cho mot resource nao (vd mapping "
            "resource type <-> database/collection, ten field, logic tao resource), "
            "agent/nguoi van hanh can tu doc source code service tuong ung -- script "
            "nay khong grep codebase."
        )

        print_header("Step 5: Ket luan")

        errors = [name for name, state in resource_states.items() if state == "error"]
        existing = [name for name, state in resource_states.items() if state == "found"]
        missing = [name for name, state in resource_states.items() if state == "empty"]

        on_system = resource_states.get("IDENTITY") == "found"
        status_line = (
            "Thiet bi DA len he thong (co IDENTITY)." if on_system
            else "Thiet bi CHUA len he thong (KHONG co IDENTITY)."
            if resource_states.get("IDENTITY") == "empty"
            else "KHONG xac dinh duoc (loi ket noi Mongo khi kiem tra IDENTITY)."
        )

        causes = []
        actions = []

        if errors:
            causes.append(
                f"Khong ket noi duoc Mongo cho: {', '.join(errors)} (loi ha tang/network, "
                "KHONG phai resource khong ton tai)."
            )
            actions.append(
                "Kiem tra ket noi toi MongoDB (vd directConnection=true neu seed host la "
                "1 member duy nhat advertise IP noi bo cho cac member khac) roi chay lai."
            )

        if not any_adapter_log:
            causes.append(
                f"Khong thay log adapter ({', '.join(adapter_services)}) trong {minutes} "
                "phut qua -- co the device_id sai, khoang thoi gian chua dung, hoac thiet "
                "bi chua gui request nao."
            )
            actions.append(f"Thu rong --minutes hoac kiem tra lai device_id={device_id}.")
        elif resource_states.get("IDENTITY") == "empty":
            causes.append("Co log adapter nhung IDENTITY chua duoc tao -- thiet bi chua dang ky xong.")
            actions.append("Kiem tra luong dang ky thiet bi (registration) o core service lien quan.")
        elif resource_states.get("AE") == "empty":
            causes.append("Co IDENTITY nhung chua co AE -- thiet bi chua tao xong Application Entity.")
            actions.append("Kiem tra log core service xu ly tao AE cho device nay.")
        elif resource_states.get("CNT") == "empty":
            causes.append("Co AE nhung chua co container (CNT) nao -- thieu buoc tao container.")
            actions.append("Kiem tra log core service xu ly tao container; xac nhan ten container ky vong.")
        elif resource_states.get("SUB") == "empty":
            causes.append("Co container nhung chua co Subscription (SUB) -- backend/AE chua subscribe.")
            actions.append("Kiem tra config subscribe cua backend AE lien quan toi container nay.")
        elif resource_states.get("CIN") == "empty":
            causes.append("Co du AE/CNT/SUB nhung chua co ContentInstance (CIN) nao duoc ghi.")
            actions.append("Kiem tra log core service xu ly ghi du lieu (CIN) cho thiet bi nay.")
        elif resource_name and resource_states.get(resource_name) == "empty":
            causes.append(f"Resource duoc hoi rieng ({resource_name}) khong ton tai du cac resource khac OK.")
            actions.append(f"Kiem tra logic tao rieng {resource_name} (doc source code, xem Step 4).")
        elif not causes:
            causes.append(
                "Tat ca resource kiem tra duoc deu ton tai -- chua phat hien diem nghen ro "
                "rang qua Mongo/log adapter; can kiem tra them notify/MQTT/EMQX hoac phia "
                "backend nhan du lieu (ngoai pham vi script nay)."
            )
            actions.append(
                "Neu van bao loi, cung cap them request_id/resource_name/error_message cu "
                "the de tra cuu sau hon (vd doc source code tuong ung, xem Step 4)."
            )

        if error_log_lines:
            error_summary = "; ".join(line[:150] for line in error_log_lines[:3])
            log_error_line = f"{len(error_log_lines)} dong co dau hieu loi (error/exception/fail/timeout/...): {error_summary}"
        elif any_adapter_log:
            log_error_line = (
                f"khong thay dong nao co tu khoa loi trong {len(adapter_log_lines)} dong log adapter da "
                "tim duoc (xem Step 2) -- cac dong nay la log request binh thuong, KHONG phai log loi."
            )
        else:
            log_error_line = "khong co log adapter nao nhac toi device_id trong khoang thoi gian da xet."

        print("Ket luan:")
        print(f"- {status_line}")
        print(f"- Cac resource da ton tai: {', '.join(existing) if existing else '(khong co)'}")
        print(f"- Cac resource con thieu: {', '.join(missing) if missing else '(khong co)'}")
        print(f"- Log loi phat hien: {log_error_line}")
        print(f"- Nguyen nhan kha nghi: {' | '.join(causes)}")
        print(f"- De xuat xu ly tiep theo: {' | '.join(actions)}")


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device_id")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--application-domain", default="")
    parser.add_argument("--resource-name", default="", choices=["", *RESOURCE_QUERIES.keys()])
    parser.add_argument("--error-message", default="")
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--adapter-services", default="iot-http-api,iot-mqtt-client-adapter")
    args = parser.parse_args()

    asyncio.run(
        run(
            args.device_id,
            args.request_id or None,
            args.application_domain or None,
            args.resource_name or None,
            args.error_message or None,
            args.minutes,
            split_csv(args.adapter_services),
        )
    )


if __name__ == "__main__":
    _main()
