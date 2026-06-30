"""Shared helpers for the runbook-automation scripts in this directory
(debug_device_command_flow.py, debug_telemetry_flow.py,
check_device_status.py). Talks to the live mcp_server/ over MCP -- same
guardrails, same auth as any other caller. Not a standalone script.

Env vars: MCP_SERVER_URL, MCP_TEST_BEARER_KEY (same as manual_test_client.py).
"""
import json
import os
import time
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

LOKI_DATASOURCE_UID = "loki"


def print_header(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def split_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def time_window(minutes):
    end = int(time.time())
    return end - minutes * 60, end


@asynccontextmanager
async def mcp_session():
    url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
    bearer_key = os.getenv("MCP_TEST_BEARER_KEY", "")
    headers = {"Authorization": f"Bearer {bearer_key}"} if bearer_key else {}

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_tool(session, tool_name, tool_args):
    """Returns (is_error, payload). Prefers structuredContent (reliable typed
    shape) over re-parsing the unstructured text content -- structuredContent
    is only populated when the server-side tool has a concrete generic return
    type (eg. list[dict[str, Any]]), see mcp_server/tools/mongo_tools.py."""
    result = await session.call_tool(tool_name, tool_args)

    if result.isError:
        text_chunks = [getattr(item, "text", str(item)) for item in result.content]
        return True, "\n".join(text_chunks)

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


def extract_loki_matches(payload):
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


async def loki_search(session, *, service_name, contains, start, end, limit=500):
    args = {
        "datasource_uid": LOKI_DATASOURCE_UID,
        "start": start,
        "end": end,
        "limit": limit,
        "contains": contains,
    }

    if service_name:
        args["service_name"] = service_name

    is_error, payload = await call_tool(session, "loki_query_range", args)

    if is_error:
        return None, payload

    matches = extract_loki_matches(payload)

    if matches is None:
        return None, payload

    return matches, None


async def grep_services(session, services, contains, start, end, *, label_prefix=""):
    """Grep a fixed list of services for a substring. Returns
    {service: [(ts_ms, line, labels), ...]}, prints as it goes."""
    found_by_service = {}

    for service in services:
        matches, error = await loki_search(
            session, service_name=service, contains=contains, start=start, end=end,
        )

        if error is not None:
            print(f"{label_prefix}[{service}] ERROR: {error}")
            found_by_service[service] = []
            continue

        if not matches:
            print(f"{label_prefix}[{service}] 0 matching line(s).")
            found_by_service[service] = []
            continue

        print(f"{label_prefix}[{service}] {len(matches)} matching line(s):")

        for ts_ms, line, _labels in sorted(matches, key=lambda item: item[0]):
            print(f"  {ts_ms}  {line[:300]}")

        found_by_service[service] = matches

    return found_by_service


async def auto_trace_from_matches(session, matches_by_service, start, end, max_trace_ids, *, extra_services=()):
    """Given {service: [(ts_ms, line, labels), ...]} (eg. from grep_services),
    pull distinct trace_id labels and search the WHOLE namespace for each one
    (no service_name filter) to discover which other services handled the
    same request -- OpenTelemetry trace_id correlates a request across every
    service it touches. Returns {service: [(ts_ms, line), ...]} for services
    other than the ones already in matches_by_service, plus any
    extra_services greped manually on top (by contains=device_id, since the
    caller doesn't know a trace_id to use for those)."""
    trace_ids = []

    for matches in matches_by_service.values():
        for _ts_ms, _line, labels in matches:
            trace_id = labels.get("trace_id")

            if trace_id and trace_id not in trace_ids:
                trace_ids.append(trace_id)

    trace_ids = trace_ids[:max_trace_ids]
    known_services = set(matches_by_service.keys())
    forwarded_hits = {}

    if not trace_ids:
        print(
            "Khong co trace_id nao trong cac dong log da tim thay o buoc truoc "
            "-> khong co gi de auto-trace."
        )
    else:
        print(f"Trace_id tim duoc: {', '.join(trace_ids)}")

        for trace_id in trace_ids:
            matches, error = await loki_search(
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

            downstream = [s for s in services_seen if s not in known_services]

            if downstream:
                print(f"[trace_id={trace_id}] request duoc chuyen tiep sang: {', '.join(downstream)}")
            else:
                print(
                    f"[trace_id={trace_id}] chi thay o "
                    f"({', '.join(services_seen.keys())}) -- KHONG thay o service "
                    "nao khac."
                )

            for service_name, lines in services_seen.items():
                if service_name in known_services:
                    continue

                forwarded_hits.setdefault(service_name, [])

                for ts_ms, line in sorted(lines):
                    print(f"  [{service_name}] {ts_ms}  {line[:300]}")
                    forwarded_hits[service_name].append((ts_ms, line))

    for service in extra_services:
        if service in forwarded_hits or service in known_services:
            continue

        print(f"(thu cong, --core-services) chua co data cho service: {service}")

    return forwarded_hits


async def mongo_find(session, label, database, collection, query, sort=None, limit=20, *, quiet_empty=False):
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

    is_error, payload = await call_tool(session, "mongo_find", args)

    if is_error:
        print(f"[{label}] ERROR (khong kiem tra duoc, KHONG phai 'khong ton tai'): {payload}")
        return "error", None

    docs = payload if isinstance(payload, list) else []
    count = len(docs)

    if not (quiet_empty and count == 0):
        print(f"[{label}] {database}.{collection} query={query} -> {count} doc(s)")

    if not isinstance(payload, list):
        print(f"  WARNING: unexpected response shape ({type(payload).__name__}): {str(payload)[:300]}")

    for doc in docs[:5]:
        print(f"  {json.dumps(doc, default=str)[:300]}")

    return ("found" if count > 0 else "empty"), docs
