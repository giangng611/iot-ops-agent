"""Automate runbook scenario 5 (luong gui lenh xuong thiet bi) against the
live mcp_server/, end to end:

  Step 2: grep adapter logs (iot-http-api, iot-mqtt-client-adapter) for the
          device_id, via loki_query_range with a server-side line filter
          (LogQL `|= "device_id"`) -- the filter runs inside Loki, so it is
          not limited by `limit`/maxLines the way client-side filtering was
          in the first version of this script (a chatty service could emit
          thousands of lines/minute; filtering after the fact silently
          missed matches outside the truncated window).
  Step 3 (AUTO): for every adapter line found in step 2, pull the line's
          `trace_id` label (OpenTelemetry trace id, present on every log line
          in this cluster) and re-run the *same* line filter with NO
          service_name restriction -- i.e. search the configured IoT platform namespace
          namespace for that trace_id. Whichever service_name shows up in the
          result (other than the adapter itself) is where the request was
          forwarded to. This replaces the old --core-services flag, which
          required a human to already know/guess the downstream service.
          --core-services is kept as an optional manual addition on top.
  Step 4: check Mongo resources (IDENTITY, AE, CNT, SUB, URI_MAPPER, CIN) via
          mongo_find -- only namespaces already on the allowlist are queried.
  Step 5: print a best-effort conclusion based on what was/wasn't found.

This only *reads* through the existing mcp_server/ tools (same guardrails,
same auth) -- it does not bypass anything. Mongo's $regex-based lookups from
the runbook (huri regex match) are intentionally NOT run here: $regex is on
BLOCKED_QUERY_OPERATORS in services/company_mongo_proxy.py and will always be
rejected -- this script only uses exact-match queries.

Usage:
  python mcp_server/scripts/debug_device_command_flow.py <device_id> [options]

Options:
  --minutes N              how far back to search Loki logs (default 60)
  --adapter-services a,b   comma list of adapter services to grep (default:
                            iot-http-api,iot-mqtt-client-adapter)
  --core-services a,b      EXTRA core services to grep on top of the
                            auto-traced ones (optional; auto-trace via
                            trace_id usually makes this unnecessary)
  --max-trace-ids N        cap how many distinct trace_id values to follow
                            in step 3 (default 5, to bound query count)
  --content-instance TEXT  also search CIN by content substring (uses Mongo
                            exact match against "con", not regex)

Env vars (same as manual_test_client.py):
  MCP_SERVER_URL, MCP_TEST_BEARER_KEY
"""
import argparse
import asyncio
import json
import os
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

LOKI_DATASOURCE_UID = "loki"


def _print_header(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


async def _call(session, tool_name, tool_args):
    result = await session.call_tool(tool_name, tool_args)

    if result.isError:
        text_chunks = [getattr(item, "text", str(item)) for item in result.content]
        return True, "\n".join(text_chunks)

    # Prefer structuredContent: the MCP SDK wraps non-object return values
    # (e.g. a bare list from mongo_find) under a "result" key per the MCP
    # spec, since structured content must be a JSON object at the top level.
    if result.structuredContent is not None:
        structured = result.structuredContent
        if isinstance(structured, dict) and list(structured.keys()) == ["result"]:
            return False, structured["result"]
        return False, structured

    text_chunks = [getattr(item, "text", str(item)) for item in result.content]
    raw = "\n".join(text_chunks)

    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = raw

    return False, parsed


def _extract_matches(payload):
    """Returns a list of (ts_ms, line, labels_dict) from a loki_query_range
    response, or None if the response shape was not what we expected."""
    matches = []

    try:
        for frame in payload["results"]["test"]["frames"]:
            values = frame["data"]["values"]
            labels_values = values[0] if len(values) > 0 else []
            ts_values = values[1] if len(values) > 1 else []
            line_values = values[2] if len(values) > 2 else []

            for ts_ms, line, labels in zip(ts_values, line_values, labels_values):
                matches.append((ts_ms, line, labels or {}))
    except (KeyError, IndexError, TypeError):
        return None

    return matches


async def _loki_search(session, *, service_name, contains, start, end, limit=500):
    args = {
        "datasource_uid": LOKI_DATASOURCE_UID,
        "start": start,
        "end": end,
        "limit": limit,
        "contains": contains,
    }

    if service_name:
        args["service_name"] = service_name

    is_error, payload = await _call(session, "loki_query_range", args)

    if is_error:
        return None, payload

    matches = _extract_matches(payload)

    if matches is None:
        return None, payload

    return matches, None


async def _step2_adapter_grep(session, adapter_services, device_id, start, end):
    found_by_service = {}

    for service in adapter_services:
        matches, error = await _loki_search(
            session, service_name=service, contains=device_id, start=start, end=end,
        )

        if error is not None:
            print(f"[{service}] ERROR: {error}")
            found_by_service[service] = []
            continue

        if not matches:
            print(f"[{service}] 0 lines mentioning device_id in this window.")
            found_by_service[service] = []
            continue

        print(f"[{service}] {len(matches)} matching line(s):")

        for ts_ms, line, _labels in sorted(matches, key=lambda item: item[0]):
            print(f"  {ts_ms}  {line[:300]}")

        found_by_service[service] = matches

    return found_by_service


async def _step3_auto_trace(session, adapter_matches_by_service, device_id, start, end, max_trace_ids, extra_core_services):
    trace_ids = []

    for matches in adapter_matches_by_service.values():
        for _ts_ms, _line, labels in matches:
            trace_id = labels.get("trace_id")

            if trace_id and trace_id not in trace_ids:
                trace_ids.append(trace_id)

    trace_ids = trace_ids[:max_trace_ids]

    if not trace_ids:
        print(
            "Khong co trace_id nao trong cac dong log adapter da tim thay o "
            "Step 2 (hoac Step 2 khong tim thay gi) -> khong co gi de auto-trace. "
            "Neu da biet core service, dung --core-services de grep thu cong."
        )
        return {}

    print(f"Trace_id tim duoc tu Step 2: {', '.join(trace_ids)}")
    adapter_service_names = set(adapter_matches_by_service.keys())
    forwarded_hits = {}

    for trace_id in trace_ids:
        matches, error = await _loki_search(
            session, service_name=None, contains=trace_id, start=start, end=end,
        )

        if error is not None:
            print(f"[trace_id={trace_id}] ERROR: {error}")
            continue

        if not matches:
            print(f"[trace_id={trace_id}] khong tim thay o bat ky service nao (la?).")
            continue

        services_seen = {}

        for ts_ms, line, labels in matches:
            service_name = labels.get("service_name", "?")
            services_seen.setdefault(service_name, []).append((ts_ms, line))

        downstream_services = [s for s in services_seen if s not in adapter_service_names]

        if downstream_services:
            print(
                f"[trace_id={trace_id}] request duoc chuyen tiep sang: "
                f"{', '.join(downstream_services)}"
            )
        else:
            print(
                f"[trace_id={trace_id}] chi thay o adapter "
                f"({', '.join(services_seen.keys())}) -- KHONG thay log o bat "
                "ky service core nao -> nghi van loi chuyen tiep tu adapter "
                "sang core."
            )

        for service_name, lines in services_seen.items():
            if service_name in adapter_service_names:
                continue

            forwarded_hits.setdefault(service_name, [])

            for ts_ms, line in sorted(lines):
                print(f"  [{service_name}] {ts_ms}  {line[:300]}")
                forwarded_hits[service_name].append((ts_ms, line))

    for service in extra_core_services:
        if service in forwarded_hits:
            continue

        print(f"(thu cong, --core-services) grep them service: {service}")
        matches, error = await _loki_search(
            session, service_name=service, contains=device_id, start=start, end=end,
        )

        if error is not None:
            print(f"[{service}] ERROR: {error}")
            continue

        if not matches:
            print(f"[{service}] 0 lines mentioning device_id in this window.")
            continue

        print(f"[{service}] {len(matches)} matching line(s):")

        for ts_ms, line, _labels in sorted(matches, key=lambda item: item[0]):
            print(f"  {ts_ms}  {line[:300]}")

        forwarded_hits[service] = [(ts_ms, line) for ts_ms, line, _ in matches]

    return forwarded_hits


async def _mongo_find(session, label, database, collection, query, sort=None, limit=20):
    """Returns (state, payload). state is "found" / "empty" / "error" -- an
    "error" (eg. Mongo unreachable) must NEVER be treated as "this resource
    does not exist", only as "could not check"."""
    args = {
        "database": database,
        "collection": collection,
        "query": query,
        "limit": limit,
    }

    if sort:
        args["sort_field"], args["sort_direction"] = sort

    is_error, payload = await _call(session, "mongo_find", args)

    if is_error:
        print(f"[{label}] ERROR (khong kiem tra duoc, KHONG phai 'khong ton tai'): {payload}")
        return "error", None

    docs = payload if isinstance(payload, list) else []
    count = len(docs)
    print(f"[{label}] {database}.{collection} query={query} -> {count} doc(s)")

    if not isinstance(payload, list):
        print(f"  WARNING: unexpected response shape ({type(payload).__name__}): {str(payload)[:300]}")

    for doc in docs[:5]:
        print(f"  {json.dumps(doc, default=str)[:300]}")

    return ("found" if count > 0 else "empty"), payload


async def run(device_id, minutes, adapter_services, core_services, content_instance, max_trace_ids):
    url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
    bearer_key = os.getenv("MCP_TEST_BEARER_KEY", "")
    headers = {"Authorization": f"Bearer {bearer_key}"} if bearer_key else {}

    end = int(time.time())
    start = end - minutes * 60

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            _print_header(f"Step 2: adapter logs for device_id={device_id} (last {minutes}m)")
            adapter_matches_by_service = await _step2_adapter_grep(
                session, adapter_services, device_id, start, end,
            )
            any_adapter_log = any(adapter_matches_by_service.values())

            _print_header("Step 3 (auto-trace via trace_id) + manual --core-services")
            core_hits = await _step3_auto_trace(
                session, adapter_matches_by_service, device_id, start, end,
                max_trace_ids, core_services,
            )
            any_core_log = any(core_hits.values())

            _print_header("Step 4: Mongo resource checks")

            identity_state, _ = await _mongo_find(
                session, "IDENTITY", "authorization", "IDENTITY", {"_id": device_id},
            )
            ae_state, _ = await _mongo_find(
                session, "AE", "subNNotif", "AE", {"_id": device_id},
            )
            cnt_by_pi_state, _ = await _mongo_find(
                session, "CNT (pi=deviceId)", "datamgmt", "CNT", {"pi": device_id},
            )
            cnt_by_cr_state, _ = await _mongo_find(
                session, "CNT (cr=deviceId)", "datamgmt", "CNT", {"cr": device_id},
            )
            sub_state, _ = await _mongo_find(
                session, "SUB (cr=deviceId)", "subNNotif", "SUB", {"cr": device_id},
            )
            uri_mapper_state, _ = await _mongo_find(
                session, "URI_MAPPER (nhuri=deviceId)", "orchestration", "URI_MAPPER",
                {"nhuri": device_id},
            )
            cin_state, _ = await _mongo_find(
                session, "CIN (cr=deviceId, sorted)", "datamgmt", "CIN", {"cr": device_id},
                sort=("ct", -1),
            )

            if content_instance:
                await _mongo_find(
                    session, "CIN (con=content_instance)", "datamgmt", "CIN",
                    {"con": content_instance}, sort=("ct", -1),
                )

            _print_header("Step 5: conclusion (best-effort)")

            mongo_states = {
                "IDENTITY": identity_state,
                "AE": ae_state,
                "CNT": "found" if "found" in (cnt_by_pi_state, cnt_by_cr_state) else (
                    "error" if "error" in (cnt_by_pi_state, cnt_by_cr_state) else "empty"
                ),
                "SUB": sub_state,
                "CIN": cin_state,
            }
            mongo_errors = [name for name, state in mongo_states.items() if state == "error"]

            if mongo_errors:
                print(
                    "- KHONG ket noi duoc Mongo cho cac resource: "
                    f"{', '.join(mongo_errors)} -> ket luan Step 4 KHONG day "
                    "du, day la loi ha tang/network (vd replica set advertise "
                    "private IP khong reachable tu may chay script nay), "
                    "KHONG duoc suy ra la resource khong ton tai. Chay lai "
                    "script tu mot may co duong mang toi duoc Mongo thuc."
                )

            if not any_adapter_log:
                print(
                    "- KHONG thay log o adapter "
                    f"({', '.join(adapter_services)}) trong {minutes} phut qua "
                    "-> he thong co the chua nhan duoc request command "
                    "(hoac device_id/khoang thoi gian khong dung, hay rong rong "
                    "lai --minutes hoac kiem tra device_id)."
                )
            elif not any_core_log:
                print(
                    "- Co log adapter nhung auto-trace (trace_id) va "
                    "--core-services (neu co) deu KHONG thay log o service "
                    "core nao -> nghi van loi chuyen tiep giua adapter va core."
                )

            if not mongo_errors:
                if mongo_states["IDENTITY"] == "empty":
                    print("- IDENTITY cua device KHONG ton tai trong authorization.IDENTITY.")
                elif mongo_states["AE"] == "empty":
                    print("- AE cua device KHONG ton tai trong subNNotif.AE.")
                elif mongo_states["CNT"] == "empty":
                    print(
                        "- KHONG tim thay container nao (CNT) gan voi device nay "
                        "trong datamgmt.CNT -> kiem tra lai resource container "
                        "(co the can tim theo huri, nhung $regex bi guardrail "
                        "chan -- query thu cong qua mongosh/Compass neu can)."
                    )
                elif mongo_states["SUB"] == "empty":
                    print(
                        "- Co container nhung KHONG tim thay subscription (SUB) "
                        "-> nghi van loi subscription/point-of-access, notify se "
                        "khong duoc gui di."
                    )
                elif mongo_states["CIN"] == "empty":
                    print(
                        "- Co subscription nhung KHONG tim thay ContentInstance "
                        "(CIN) nao gan voi device -> CIN chua duoc tao, loi xu ly "
                        "resource/database o tang ghi du lieu."
                    )
                else:
                    print(
                        "- Da co IDENTITY, AE, container, subscription, va CIN "
                        "gan nhat -> luong ghi du lieu OK; neu device van khong "
                        "nhan duoc lenh thi nghi van nam o tang notify/MQTT/EMQX "
                        "hoac ket noi thiet bi (ngoai pham vi cua script nay)."
                    )

            if uri_mapper_state == "empty":
                print(
                    "- (Phu) KHONG tim thay URI_MAPPER voi nhuri=device_id -- "
                    "thu lai voi AE id / container id / sub id thuc te neu "
                    "biet, vi nhuri co the tro toi entity khac, khong phai "
                    "deviceId truc tiep."
                )


def _split_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device_id")
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument(
        "--adapter-services",
        default="iot-http-api,iot-mqtt-client-adapter",
    )
    parser.add_argument("--core-services", default="")
    parser.add_argument("--max-trace-ids", type=int, default=5)
    parser.add_argument("--content-instance", default="")
    args = parser.parse_args()

    asyncio.run(
        run(
            args.device_id,
            args.minutes,
            _split_csv(args.adapter_services),
            _split_csv(args.core_services),
            args.content_instance or None,
            args.max_trace_ids,
        )
    )
