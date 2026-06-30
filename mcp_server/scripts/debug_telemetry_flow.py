"""Automate runbook scenario 6 (luong telemetry tu thiet bi gui len) against
the live mcp_server/:

  Step 2: grep adapter logs (iot-http-api, iot-mqtt-client-adapter) for the
          device_id -- if nothing found, telemetry never reached the system.
  Step 3: check whether the device has a "cnt_telemetry" container: query
          datamgmt.CNT by pi=device_id and cr=device_id, then flag any result
          whose serialized fields mention "telemetry" (resource/container
          naming field is not guaranteed across deployments -- this is a
          best-effort substring match, not an exact schema assumption).
  Step 4: check whether a ContentInstance (CIN) was created under that
          container -- query datamgmt.CIN by pi=container_id (if Step 3 found
          one) and by cr=device_id, sorted by ct desc (latest first).
  Step 5: check whether the backend AE has a Subscription (SUB) on
          cnt_telemetry -- query subNNotif.SUB by cr=device_id and, if known,
          --ae-id.
  Step 6: check notify logs -- auto-trace (via trace_id, same mechanism as
          scenario 5) from whatever adapter/CIN-related log lines were found,
          to see which service(s) handled the notify; also greps explicitly
          for "--ae-id" (or device_id if not given) across the whole
          namespace and highlights lines containing "notify"/"NOTIFY".
  Step 7: best-effort conclusion against the failure modes listed in the
          runbook.

This only *reads* through mcp_server/ tools (same guardrails/auth as any
other caller) -- $regex lookups from the runbook (huri partial match) are
intentionally NOT run: $regex is on BLOCKED_QUERY_OPERATORS in
services/company_mongo_proxy.py and is always rejected.

Usage:
  python mcp_server/scripts/debug_telemetry_flow.py <device_id> [options]

Options:
  --ae-id ID               backend AE id expected to receive notify (used to
                            narrow Step 5/Step 6 checks; optional)
  --request-id ID          request id from the runbook input, printed only
                            (not currently used to filter queries)
  --telemetry-content TEXT substring to also search CIN "con" field for
                            (exact match, not regex)
  --minutes N              how far back to search Loki logs (default 60)
  --adapter-services a,b   comma list of adapter services to grep (default:
                            iot-http-api,iot-mqtt-client-adapter)
  --max-trace-ids N        cap how many distinct trace_id values to follow
                            in Step 6 (default 5)

Env vars (same as manual_test_client.py): MCP_SERVER_URL, MCP_TEST_BEARER_KEY
"""
import argparse
import asyncio
import json
import time

from _debug_common import (
    auto_trace_from_matches,
    grep_services,
    loki_search,
    mcp_session,
    mongo_find,
    print_header,
    split_csv,
    time_window,
)


def _looks_like_telemetry_container(doc):
    blob = json.dumps(doc, default=str).lower()
    return "telemetry" in blob


async def _step3_check_container(session, device_id):
    by_pi, docs_pi = await mongo_find(
        session, "CNT (pi=deviceId)", "datamgmt", "CNT", {"pi": device_id},
    )
    by_cr, docs_cr = await mongo_find(
        session, "CNT (cr=deviceId)", "datamgmt", "CNT", {"cr": device_id},
    )

    all_docs = (docs_pi or []) + (docs_cr or [])
    telemetry_docs = [doc for doc in all_docs if _looks_like_telemetry_container(doc)]

    if telemetry_docs:
        print(
            f"-> {len(telemetry_docs)} container doc(s) trong so {len(all_docs)} "
            "co nhac toi 'telemetry' (best-effort substring match, khong dam bao "
            "dung field ten resource cua deployment nay):"
        )
        for doc in telemetry_docs[:5]:
            print(f"  {json.dumps(doc, default=str)[:300]}")
    elif all_docs:
        print(
            f"-> Co {len(all_docs)} container (CNT) gan voi device nhung KHONG co "
            "doc nao nhac toi 'telemetry' -- co the container ton tai nhung dat "
            "ten khac, hoac day khong phai container telemetry."
        )

    state = "error" if "error" in (by_pi, by_cr) else (
        "found" if all_docs else "empty"
    )
    container_id = telemetry_docs[0].get("_id") if telemetry_docs else None
    return state, container_id, all_docs


async def run(device_id, ae_id, request_id, telemetry_content, minutes, adapter_services, max_trace_ids):
    start, end = time_window(minutes)

    async with mcp_session() as session:
        print_header(
            f"Step 1: input -- device_id={device_id} ae_id={ae_id or '(chua biet)'} "
            f"request_id={request_id or '(chua biet)'} minutes={minutes}"
        )

        print_header(f"Step 2: adapter logs for device_id={device_id} (last {minutes}m)")
        adapter_hits = await grep_services(session, adapter_services, device_id, start, end)
        any_adapter_log = any(adapter_hits.values())

        print_header("Step 3: container cnt_telemetry?")
        container_state, container_id, _container_docs = await _step3_check_container(session, device_id)

        print_header("Step 4: ContentInstance (CIN) telemetry")
        cin_queries_run = []

        if container_id:
            cin_state_pi, _ = await mongo_find(
                session, "CIN (pi=container_id, sorted)", "datamgmt", "CIN",
                {"pi": container_id}, sort=("ct", -1),
            )
            cin_queries_run.append(cin_state_pi)

        cin_state_cr, _ = await mongo_find(
            session, "CIN (cr=deviceId, sorted)", "datamgmt", "CIN",
            {"cr": device_id}, sort=("ct", -1),
        )
        cin_queries_run.append(cin_state_cr)

        if telemetry_content:
            cin_state_con, _ = await mongo_find(
                session, "CIN (con=telemetry_content, sorted)", "datamgmt", "CIN",
                {"con": telemetry_content}, sort=("ct", -1),
            )
            cin_queries_run.append(cin_state_con)

        cin_state = "error" if "error" in cin_queries_run else (
            "found" if "found" in cin_queries_run else "empty"
        )

        print_header("Step 5: Subscription (SUB) tren cnt_telemetry")
        sub_query = {"cr": device_id}
        sub_label = "SUB (cr=deviceId)"

        if ae_id:
            sub_query = {"cr": ae_id}
            sub_label = "SUB (cr=ae_id)"

        sub_state, _ = await mongo_find(session, sub_label, "subNNotif", "SUB", sub_query)

        if container_id:
            sub_state_pi, _ = await mongo_find(
                session, "SUB (pi=container_id)", "subNNotif", "SUB", {"pi": container_id},
            )
            sub_state = "found" if "found" in (sub_state, sub_state_pi) else (
                "error" if "error" in (sub_state, sub_state_pi) else "empty"
            )

        print_header("Step 6: notify log (auto-trace + keyword search)")
        notify_search_term = ae_id or device_id
        forwarded = await auto_trace_from_matches(
            session, adapter_hits, start, end, max_trace_ids,
        )
        any_notify_trace = any(forwarded.values())

        notify_matches, notify_error = await loki_search(
            session, service_name=None, contains=notify_search_term, start=start, end=end, limit=500,
        )

        if notify_error is not None:
            print(f"[notify keyword search] ERROR: {notify_error}")
        elif notify_matches:
            notify_lines = [
                (ts_ms, line, labels) for ts_ms, line, labels in notify_matches
                if "notify" in line.lower()
            ]
            print(
                f"[notify keyword search] {len(notify_matches)} dong nhac toi "
                f"'{notify_search_term}', trong do {len(notify_lines)} dong co chua "
                "tu khoa 'notify':"
            )
            for ts_ms, line, labels in sorted(notify_lines, key=lambda item: item[0])[:20]:
                service = labels.get("service_name", "?")
                print(f"  [{service}] {ts_ms}  {line[:300]}")
        else:
            print(f"[notify keyword search] 0 dong nhac toi '{notify_search_term}'.")

        any_notify_log = any_notify_trace or bool(notify_matches)

        print_header("Step 7: conclusion (best-effort)")

        mongo_states = {
            "CNT (telemetry container)": container_state,
            "CIN": cin_state,
            "SUB": sub_state,
        }
        mongo_errors = [name for name, state in mongo_states.items() if state == "error"]

        if mongo_errors:
            print(
                "- KHONG ket noi duoc Mongo cho: "
                f"{', '.join(mongo_errors)} -> ket luan Step 3-5 KHONG day du, day "
                "la loi ha tang/network, KHONG duoc suy ra la resource khong ton tai."
            )

        if not any_adapter_log:
            print(
                "- KHONG thay log o adapter "
                f"({', '.join(adapter_services)}) trong {minutes} phut qua -> "
                "thiet bi chua gui telemetry toi he thong (hoac device_id/khoang "
                "thoi gian sai)."
            )
        elif not mongo_errors and container_state == "empty":
            print(
                "- Co log adapter (thiet bi co gui ban tin) nhung KHONG tim thay "
                "container nao -> nghi van thiet bi/AE chua tao du container "
                "cnt_telemetry, hoac field/schema cua collection CNT trong "
                "deployment nay khac voi gia dinh (pi/cr=deviceId)."
            )
        elif not mongo_errors and cin_state == "empty":
            print(
                "- Container ton tai nhung KHONG tao duoc ContentInstance (CIN) "
                "-> loi ghi du lieu telemetry vao container (kiem tra log core "
                "service xu ly ghi CIN)."
            )
        elif not mongo_errors and sub_state == "empty":
            print(
                "- Co CIN (telemetry da duoc ghi) nhung backend AE KHONG co "
                "Subscription (SUB) tren container nay -> backend chua subscribe, "
                "se khong nhan duoc notify du telemetry da len he thong."
            )
        elif not mongo_errors and not any_notify_log:
            print(
                "- Co CIN + SUB nhung KHONG tim thay log notify nao (qua auto-trace "
                "hoac tu khoa) -> nghi van notify gui thi bai, hoac point-of-access "
                "cua backend AE sai/khong reachable."
            )
        elif not mongo_errors:
            print(
                "- Co container, CIN, SUB, va co dau hieu notify -> luong telemetry "
                "co ve OK toi buoc notify; neu backend van bao khong nhan duoc, nghi "
                "van nam o phia backend (xu ly notify loi/khong phan hoi) -- ngoai "
                "pham vi log cua he thong nay."
            )


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device_id")
    parser.add_argument("--ae-id", default="")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--telemetry-content", default="")
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--adapter-services", default="iot-http-api,iot-mqtt-client-adapter")
    parser.add_argument("--max-trace-ids", type=int, default=5)
    args = parser.parse_args()

    asyncio.run(
        run(
            args.device_id,
            args.ae_id or None,
            args.request_id or None,
            args.telemetry_content or None,
            args.minutes,
            split_csv(args.adapter_services),
            args.max_trace_ids,
        )
    )


if __name__ == "__main__":
    _main()
