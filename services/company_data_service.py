import os
import re
import json

import psycopg
from psycopg.rows import dict_row
from pymongo import MongoClient

from storage.sqlite_store import (
    get_all_latest_devices as get_sqlite_latest_devices,
    get_latest_status as get_sqlite_latest_status,
)


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_TABLE_LIMIT = 20
DEFAULT_PREVIEW_LIMIT = 5
MAX_PREVIEW_LIMIT = 20
MAX_TEXT_VALUE_CHARS = 160
MAX_COLUMNS = 24
MAX_MONGO_FIELDS = 32
MAX_SCHEMA_SAMPLE_DOCUMENTS = 20
MAX_SCHEMA_FIELD_PATHS = 120
MAX_PAYLOAD_CHARS_TO_PARSE = 20000
DEFAULT_OPERATIONAL_RECORD_LIMIT = 30
MAX_THRESHOLD_SCAN_RECORDS = 80
MAX_THRESHOLD_MATCHES = 20
MAX_DISPLAY_METRICS = 8


def get_company_db_url():
    return (
        os.getenv("COMPANY_DB_URL")
        or os.getenv("COMPANY_POSTGRES_URL")
        or os.getenv("IOT_PLATFORM_DB_URL")
    )


def get_company_mongodb_uri():
    return (
        os.getenv("COMPANY_MONGODB_URI")
        or os.getenv("COMPANY_MONGO_URI")
        or os.getenv("IOT_PLATFORM_MONGODB_URI")
    )


def get_company_mongodb_db():
    return os.getenv("COMPANY_MONGODB_DB", "").strip()


def company_db_configured():
    return bool(get_company_db_url() or get_company_mongodb_uri())


def company_db_type():
    if get_company_mongodb_uri():
        return "mongodb"

    if get_company_db_url():
        return "postgres"

    return "none"


def get_company_connection():
    url = get_company_db_url()

    if not url:
        raise RuntimeError(
            "COMPANY_DB_URL, COMPANY_POSTGRES_URL, or IOT_PLATFORM_DB_URL "
            "is not configured."
        )

    return psycopg.connect(
        url,
        connect_timeout=int(os.getenv("COMPANY_DB_CONNECT_TIMEOUT_SECONDS", "5")),
        row_factory=dict_row,
        prepare_threshold=None,
    )


def get_company_mongo_client():
    uri = get_company_mongodb_uri()

    if not uri:
        raise RuntimeError(
            "COMPANY_MONGODB_URI, COMPANY_MONGO_URI, or "
            "IOT_PLATFORM_MONGODB_URI is not configured."
        )

    timeout_ms = int(os.getenv("COMPANY_DB_CONNECT_TIMEOUT_SECONDS", "5")) * 1000
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=int(os.getenv("COMPANY_DB_STATEMENT_TIMEOUT_MS", "5000")),
    )
    client.admin.command("ping")
    return client


def set_read_only_guardrails(cursor):
    cursor.execute("set transaction read only")
    cursor.execute(
        "set local statement_timeout = %s",
        (os.getenv("COMPANY_DB_STATEMENT_TIMEOUT_MS", "5000"),),
    )


def list_company_tables(limit=DEFAULT_TABLE_LIMIT):
    safe_limit = max(1, min(int(limit), 100))

    with get_company_connection() as conn:
        with conn.cursor() as cursor:
            set_read_only_guardrails(cursor)
            cursor.execute(
                """
                select n.nspname as schema_name,
                       c.relname as table_name,
                       greatest(c.reltuples::bigint, 0) as estimated_rows
                from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where c.relkind in ('r', 'p', 'v', 'm')
                  and n.nspname not in (
                    'pg_catalog',
                    'information_schema',
                    'pg_toast'
                  )
                order by n.nspname, c.relname
                limit %s
                """,
                (safe_limit,),
            )
            return [dict(row) for row in cursor.fetchall()]


def list_company_columns(schema_name, table_name):
    with get_company_connection() as conn:
        with conn.cursor() as cursor:
            set_read_only_guardrails(cursor)
            cursor.execute(
                """
                select column_name, data_type
                from information_schema.columns
                where table_schema = %s
                  and table_name = %s
                order by ordinal_position
                limit %s
                """,
                (schema_name, table_name, MAX_COLUMNS),
            )
            return [dict(row) for row in cursor.fetchall()]


def validate_identifier(value, label):
    if not IDENTIFIER_RE.match(value or ""):
        raise ValueError(f"Invalid {label}: {value}")


def trim_value(value):
    if isinstance(value, str) and len(value) > MAX_TEXT_VALUE_CHARS:
        return f"{value[:MAX_TEXT_VALUE_CHARS]}..."

    return value


def trim_document(value):
    if isinstance(value, dict):
        return {
            key: trim_document(nested_value)
            for key, nested_value in list(value.items())[:MAX_MONGO_FIELDS]
        }

    if isinstance(value, list):
        return [trim_document(item) for item in value[:10]]

    return trim_value(value)


def describe_value_type(value):
    if value is None:
        return "null"

    if isinstance(value, bool):
        return "bool"

    if isinstance(value, int):
        return "int"

    if isinstance(value, float):
        return "float"

    if isinstance(value, str):
        return "str"

    if isinstance(value, dict):
        return "object"

    if isinstance(value, list):
        return "array"

    return type(value).__name__


def collect_field_types(value, path, fields):
    if len(fields) >= MAX_SCHEMA_FIELD_PATHS:
        return

    value_type = describe_value_type(value)

    if path:
        field = fields.setdefault(path, {"types": set(), "count": 0})
        field["types"].add(value_type)
        field["count"] += 1

    if isinstance(value, dict):
        for key, nested_value in list(value.items())[:MAX_MONGO_FIELDS]:
            nested_path = f"{path}.{key}" if path else key
            collect_field_types(nested_value, nested_path, fields)

    if isinstance(value, list) and value:
        collect_field_types(value[0], f"{path}[]" if path else "[]", fields)


def collect_numeric_values(value, path, values):
    if isinstance(value, bool):
        return

    if isinstance(value, (int, float)):
        values.append({
            "path": path or "value",
            "value": value,
        })
        return

    if isinstance(value, dict):
        for key, nested_value in list(value.items())[:MAX_MONGO_FIELDS]:
            nested_path = f"{path}.{key}" if path else key
            collect_numeric_values(nested_value, nested_path, values)
        return

    if isinstance(value, list):
        for index, item in enumerate(value[:10]):
            collect_numeric_values(item, f"{path}[{index}]", values)


def collect_display_metrics(value, path, metrics):
    if len(metrics) >= MAX_DISPLAY_METRICS:
        return

    if isinstance(value, bool):
        metrics.append({
            "name": path or "value",
            "value": value,
            "type": "bool",
        })
        return

    if isinstance(value, (int, float, str)):
        metrics.append({
            "name": path or "value",
            "value": trim_value(value),
            "type": describe_value_type(value),
        })
        return

    if isinstance(value, dict):
        for key, nested_value in list(value.items())[:MAX_MONGO_FIELDS]:
            nested_path = f"{path}.{key}" if path else key
            collect_display_metrics(nested_value, nested_path, metrics)

            if len(metrics) >= MAX_DISPLAY_METRICS:
                break
        return

    if isinstance(value, list):
        for index, item in enumerate(value[:5]):
            collect_display_metrics(item, f"{path}[{index}]", metrics)

            if len(metrics) >= MAX_DISPLAY_METRICS:
                break


def parse_payload_value(value):
    if not isinstance(value, str):
        return value

    compact_value = value.strip()

    if not compact_value or len(compact_value) > MAX_PAYLOAD_CHARS_TO_PARSE:
        return None

    try:
        return json.loads(compact_value)
    except ValueError:
        return None


def preview_company_table(schema_name, table_name, limit=DEFAULT_PREVIEW_LIMIT):
    validate_identifier(schema_name, "schema name")
    validate_identifier(table_name, "table name")
    safe_limit = max(1, min(int(limit), MAX_PREVIEW_LIMIT))

    with get_company_connection() as conn:
        with conn.cursor() as cursor:
            set_read_only_guardrails(cursor)
            cursor.execute(
                """
                select column_name
                from information_schema.columns
                where table_schema = %s
                  and table_name = %s
                order by ordinal_position
                limit %s
                """,
                (schema_name, table_name, MAX_COLUMNS),
            )
            columns = [row["column_name"] for row in cursor.fetchall()]

            if not columns:
                raise RuntimeError(f"Table not found: {schema_name}.{table_name}")

            selected_columns = ", ".join(
                f'"{column}"'
                for column in columns
                if IDENTIFIER_RE.match(column)
            )

            if not selected_columns:
                raise RuntimeError(
                    f"No preview-safe columns found for {schema_name}.{table_name}"
                )

            cursor.execute(
                f'select {selected_columns} from "{schema_name}"."{table_name}" limit %s',
                (safe_limit,),
            )
            rows = []

            for row in cursor.fetchall():
                rows.append({
                    key: trim_value(value)
                    for key, value in dict(row).items()
                })

            return {
                "schema": schema_name,
                "table": table_name,
                "limit": safe_limit,
                "columns": columns,
                "rows": rows,
            }


def list_company_mongo_collections(limit=DEFAULT_TABLE_LIMIT):
    safe_limit = max(1, min(int(limit), 100))
    configured_db = get_company_mongodb_db()

    with get_company_mongo_client() as client:
        database_names = (
            [configured_db]
            if configured_db
            else [
                name for name in client.list_database_names()
                if name not in {"admin", "config", "local"}
            ]
        )
        collections = []

        for database_name in database_names:
            database = client[database_name]

            for collection_name in database.list_collection_names()[:safe_limit]:
                stats = database.command(
                    "collStats",
                    collection_name,
                    scale=1,
                    maxTimeMS=int(os.getenv("COMPANY_DB_STATEMENT_TIMEOUT_MS", "5000")),
                )
                collections.append({
                    "database": database_name,
                    "collection": collection_name,
                    "estimated_documents": stats.get("count", 0),
                    "avg_document_size": stats.get("avgObjSize"),
                })

                if len(collections) >= safe_limit:
                    return collections

        return collections


def preview_company_mongo_collection(
    database_name,
    collection_name,
    limit=DEFAULT_PREVIEW_LIMIT,
):
    validate_identifier(database_name, "database name")
    validate_identifier(collection_name, "collection name")
    safe_limit = max(1, min(int(limit), MAX_PREVIEW_LIMIT))

    with get_company_mongo_client() as client:
        collection = client[database_name][collection_name]
        rows = list(
            collection.find({}, {"_id": 0})
            .max_time_ms(int(os.getenv("COMPANY_DB_STATEMENT_TIMEOUT_MS", "5000")))
            .limit(safe_limit)
        )

        return {
            "database": database_name,
            "collection": collection_name,
            "limit": safe_limit,
            "documents": [trim_document(row) for row in rows],
        }


def inspect_company_mongo_collection_schema(
    database_name,
    collection_name,
    sample_limit=DEFAULT_PREVIEW_LIMIT,
):
    validate_identifier(database_name, "database name")
    validate_identifier(collection_name, "collection name")
    safe_limit = max(1, min(int(sample_limit), MAX_SCHEMA_SAMPLE_DOCUMENTS))

    with get_company_mongo_client() as client:
        collection = client[database_name][collection_name]
        rows = list(
            collection.find({}, {"_id": 0})
            .max_time_ms(int(os.getenv("COMPANY_DB_STATEMENT_TIMEOUT_MS", "5000")))
            .limit(safe_limit)
        )
        fields = {}

        for row in rows:
            collect_field_types(row, "", fields)

        return {
            "database": database_name,
            "collection": collection_name,
            "sampled_documents": len(rows),
            "fields": [
                {
                    "path": path,
                    "types": sorted(value["types"]),
                    "sample_count": value["count"],
                }
                for path, value in sorted(fields.items())
            ][:MAX_SCHEMA_FIELD_PATHS],
        }


def inspect_company_mongo_payload_schema(
    database_name,
    collection_name,
    payload_field="con",
    sample_limit=DEFAULT_PREVIEW_LIMIT,
):
    validate_identifier(database_name, "database name")
    validate_identifier(collection_name, "collection name")
    validate_identifier(payload_field, "payload field")
    safe_limit = max(1, min(int(sample_limit), MAX_SCHEMA_SAMPLE_DOCUMENTS))

    with get_company_mongo_client() as client:
        collection = client[database_name][collection_name]
        rows = list(
            collection.find(
                {payload_field: {"$exists": True}},
                {"_id": 0, payload_field: 1, "cnf": 1},
            )
            .max_time_ms(int(os.getenv("COMPANY_DB_STATEMENT_TIMEOUT_MS", "5000")))
            .limit(safe_limit)
        )
        fields = {}
        parseable_count = 0
        content_formats = {}

        for row in rows:
            content_format = row.get("cnf")

            if content_format:
                content_formats[content_format] = (
                    content_formats.get(content_format, 0) + 1
                )

            parsed_payload = parse_payload_value(row.get(payload_field))

            if parsed_payload is None:
                continue

            parseable_count += 1
            collect_field_types(parsed_payload, "", fields)

        return {
            "database": database_name,
            "collection": collection_name,
            "payload_field": payload_field,
            "sampled_documents": len(rows),
            "parseable_payloads": parseable_count,
            "content_formats": content_formats,
            "payload_fields": [
                {
                    "path": path,
                    "types": sorted(value["types"]),
                    "sample_count": value["count"],
                }
                for path, value in sorted(fields.items())
            ][:MAX_SCHEMA_FIELD_PATHS],
        }


def parse_company_timestamp(value):
    if value is None or value == "":
        return None

    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)

    text = str(abs(number))

    if len(text) >= 13:
        number = number / 1000

    return number


def summarize_payload(payload):
    parsed_payload = parse_payload_value(payload)

    if isinstance(parsed_payload, dict):
        return {
            "payload_type": "json",
            "field_count": len(parsed_payload),
            "fields": list(parsed_payload.keys())[:12],
        }

    if isinstance(parsed_payload, list):
        return {
            "payload_type": "json_array",
            "item_count": len(parsed_payload),
        }

    if isinstance(payload, str):
        return {
            "payload_type": "text",
            "preview": trim_value(payload),
        }

    return {
        "payload_type": describe_value_type(payload),
    }


def extract_display_metrics(payload):
    parsed_payload = parse_payload_value(payload)
    metrics = []

    if isinstance(parsed_payload, dict):
        element_list = (
            parsed_payload.get("elements")
            or parsed_payload.get("e")
            or parsed_payload.get("measurements")
        )

        if isinstance(element_list, list):
            for element in element_list[:MAX_DISPLAY_METRICS]:
                if not isinstance(element, dict):
                    continue

                name = (
                    element.get("name")
                    or element.get("n")
                    or element.get("key")
                    or element.get("metric")
                )
                value = (
                    element.get("value")
                    if "value" in element
                    else element.get("v")
                    if "v" in element
                    else element.get("sv")
                    if "sv" in element
                    else element.get("bv")
                )

                if name and value is not None:
                    metrics.append({
                        "name": str(name),
                        "value": trim_value(value),
                        "type": describe_value_type(value),
                    })

            if metrics:
                return metrics

    if parsed_payload is not None:
        collect_display_metrics(parsed_payload, "", metrics)

    return metrics


def list_company_operational_records(limit=DEFAULT_OPERATIONAL_RECORD_LIMIT):
    safe_limit = max(1, min(int(limit), 100))
    database_name = os.getenv("COMPANY_OPERATIONAL_DB", "datamgmt")
    collection_name = os.getenv("COMPANY_OPERATIONAL_COLLECTION", "CIN")

    validate_identifier(database_name, "database name")
    validate_identifier(collection_name, "collection name")

    with get_company_mongo_client() as client:
        collection = client[database_name][collection_name]
        rows = list(
            collection.find(
                {},
                {
                    "_id": 0,
                    "rn": 1,
                    "pi": 1,
                    "ct": 1,
                    "lt": 1,
                    "cnf": 1,
                    "con": 1,
                    "tenantId": 1,
                    "tenantName": 1,
                    "appDomainId": 1,
                    "appDomainName": 1,
                },
            )
            .sort("ct", -1)
            .max_time_ms(int(os.getenv("COMPANY_DB_STATEMENT_TIMEOUT_MS", "5000")))
            .limit(safe_limit)
        )

    records = []

    for index, row in enumerate(rows, start=1):
        payload_summary = summarize_payload(row.get("con"))
        record_id = row.get("rn") or f"company-record-{index}"
        timestamp = row.get("lt") or row.get("ct")

        records.append({
            "device_id": str(record_id),
            "status": "unknown",
            "cpu_usage": None,
            "memory_usage": None,
            "heartbeat_delay": None,
            "timestamp": timestamp,
            "company_record": True,
            "rules_status": "not_configured",
            "content_format": row.get("cnf"),
            "parent_container": str(row.get("pi") or ""),
            "tenant_name": row.get("tenantName"),
            "app_domain_name": row.get("appDomainName"),
            "payload_summary": payload_summary,
            "metrics": extract_display_metrics(row.get("con")),
        })

    return records


def get_company_operational_payload(limit=DEFAULT_OPERATIONAL_RECORD_LIMIT):
    if company_db_type() != "mongodb":
        return simulator_fallback_snapshot(
            "Company MongoDB URL is not configured."
        )

    try:
        records = list_company_operational_records(limit)
    except Exception as exc:
        return simulator_fallback_snapshot(
            f"Company MongoDB read failed: {exc}"
        )

    return {
        "source": "company_mongodb",
        "selected_source": "company",
        "active_source": "company_mongodb",
        "rules_status": "not_configured",
        "rules_message": (
            "Company alert rules are not configured yet. These records are "
            "raw company data summaries and are not classified as alerts."
        ),
        "devices": records,
        "alerts": {
            "critical_count": 0,
            "warning_count": 0,
            "rules_status": "not_configured",
            "message": (
                "Company alert rules are not configured yet. Alert counts "
                "are intentionally not derived from raw records."
            ),
        },
    }


def scan_company_payload_threshold(threshold, limit=MAX_THRESHOLD_SCAN_RECORDS):
    safe_limit = max(1, min(int(limit), MAX_THRESHOLD_SCAN_RECORDS))
    database_name = os.getenv("COMPANY_OPERATIONAL_DB", "datamgmt")
    collection_name = os.getenv("COMPANY_OPERATIONAL_COLLECTION", "CIN")

    validate_identifier(database_name, "database name")
    validate_identifier(collection_name, "collection name")

    with get_company_mongo_client() as client:
        collection = client[database_name][collection_name]
        rows = list(
            collection.find(
                {"con": {"$exists": True}},
                {
                    "_id": 0,
                    "rn": 1,
                    "pi": 1,
                    "ct": 1,
                    "lt": 1,
                    "con": 1,
                    "tenantName": 1,
                    "appDomainName": 1,
                },
            )
            .sort("ct", -1)
            .max_time_ms(int(os.getenv("COMPANY_DB_STATEMENT_TIMEOUT_MS", "5000")))
            .limit(safe_limit)
        )

    matches = []
    parseable_payloads = 0

    for row in rows:
        parsed_payload = parse_payload_value(row.get("con"))

        if not isinstance(parsed_payload, (dict, list, int, float)):
            continue

        parseable_payloads += 1
        numeric_values = []
        collect_numeric_values(parsed_payload, "", numeric_values)

        for numeric_value in numeric_values:
            if numeric_value["value"] > threshold:
                matches.append({
                    "record_id": row.get("rn"),
                    "parent_container": row.get("pi"),
                    "timestamp": row.get("lt") or row.get("ct"),
                    "field": numeric_value["path"],
                    "value": numeric_value["value"],
                    "tenant_name": row.get("tenantName"),
                    "app_domain_name": row.get("appDomainName"),
                })

                if len(matches) >= MAX_THRESHOLD_MATCHES:
                    break

        if len(matches) >= MAX_THRESHOLD_MATCHES:
            break

    return {
        "source": "company_mongodb",
        "rules_status": "not_configured",
        "threshold": threshold,
        "scanned_records": len(rows),
        "parseable_payloads": parseable_payloads,
        "match_count": len(matches),
        "matches": matches,
        "note": (
            "This is a manual threshold scan over raw company payloads, not "
            "an approved company alert rule."
        ),
    }


def simulator_fallback_snapshot(reason):
    devices = get_sqlite_latest_devices()
    unhealthy = [
        device for device in devices
        if device["status"] in ["warning", "critical"]
    ]
    alarms = []

    for device in devices:
        latest = get_sqlite_latest_status(device["device_id"])

        if latest and latest["alarm_name"]:
            alarms.append({
                "device_id": latest["device_id"],
                "timestamp": latest["timestamp"],
                "alarm": latest["alarm_name"],
                "severity": latest["alarm_severity"],
                "status": latest["status"],
                "cpu_usage": latest["cpu_usage"],
                "memory_usage": latest["memory_usage"],
                "heartbeat_delay": latest["heartbeat_delay"],
            })

    return {
        "source": "simulator_fallback",
        "reason": reason,
        "system_overview": {
            "total_devices": len(devices),
            "healthy_count": len([
                device for device in devices
                if device["status"] == "healthy"
            ]),
            "warning_count": len([
                device for device in devices
                if device["status"] == "warning"
            ]),
            "critical_count": len([
                device for device in devices
                if device["status"] == "critical"
            ]),
            "unhealthy_devices": unhealthy,
        },
        "system_alarms": {
            "total_alarms": len(alarms),
            "active_alarms": alarms,
        },
    }


def probe_company_db(table_limit=DEFAULT_TABLE_LIMIT):
    if not company_db_configured():
        return simulator_fallback_snapshot("Company DB URL is not configured.")

    try:
        if company_db_type() == "mongodb":
            collections = list_company_mongo_collections(table_limit)
            return {
                "source": "company_mongodb",
                "collections": collections,
            }

        tables = list_company_tables(table_limit)
    except Exception as exc:
        return simulator_fallback_snapshot(
            f"Company DB probe failed: {exc}"
        )

    return {
        "source": "company_postgres",
        "tables": tables,
    }
