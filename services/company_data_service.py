import os
import re
import json

import psycopg
from psycopg.rows import dict_row

from storage.sqlite_store import (
    get_all_latest_devices as get_sqlite_latest_devices,
    get_latest_status as get_sqlite_latest_status,
)
from services.company_mongo_proxy import get_company_mongo_read_proxy
from services.company_poc_rule_service import (
    evaluate_company_poc_rules,
    get_company_poc_rule_catalog,
)
from services.grafana_tool_registry import load_grafana_kpi_rules


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
DEFAULT_OPERATIONAL_RECORD_LIMIT = 100
DEFAULT_COMPANY_CIN_SCAN_LIMIT = 500
DEFAULT_COMPANY_CIN_PER_DEVICE_LIMIT = 20
DEFAULT_COMPANY_CIN_SORT = ("_id", -1)
MAX_COMPANY_INVENTORY_RECORDS = 1000
MAX_THRESHOLD_SCAN_RECORDS = 80
MAX_THRESHOLD_MATCHES = 20
MAX_DISPLAY_METRICS = 8
MAX_AGENT_SAMPLE_RECORDS = 5
DEVICE_ID_PREFIXES = ("dvi-", "dvi_", "nod_", "cnt-", "cnt_")
CONNECTED_STATUS_VALUES = {
    "active",
    "connected",
    "online",
    "true",
    "1",
}
DISCONNECTED_STATUS_VALUES = {
    "disconnected",
    "inactive",
    "offline",
    "false",
    "0",
}
SEMANTIC_METRIC_NAMES = {
    "deviceid",
    "device_id",
    "devicename",
    "device_name",
    "id",
    "name",
    "status",
    "connectionstatus",
    "timestamp",
}
THRESHOLD_METADATA_FIELDS = {
    "ct",
    "lt",
    "pi",
    "rn",
    "timestamp",
    "time",
    "createdat",
    "updatedat",
    "locationid",
    "operatorid",
    "inventorysessionid",
    "tenantid",
    "appdomainid",
}
ONEM2M_RESOURCE_SAMPLE_LIMIT = 5


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


def normalized_metric_leaf_name(path):
    normalized = str(path or "").strip().lower()

    if not normalized:
        return ""

    normalized = normalized.rsplit(".", 1)[-1]
    normalized = normalized.split("[", 1)[0]
    return re.sub(r"[^a-z0-9_]", "", normalized)


def configured_threshold_metric_names():
    names = set()

    for rule in get_company_poc_rule_catalog().get("rules") or []:
        for name in rule.get("metric_names") or []:
            normalized = normalized_metric_leaf_name(name)

            if normalized:
                names.add(normalized)

    return names


def is_configured_threshold_metric(path):
    leaf_name = normalized_metric_leaf_name(path)

    if not leaf_name or leaf_name in THRESHOLD_METADATA_FIELDS:
        return False

    return leaf_name in configured_threshold_metric_names()


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

    with get_company_mongo_read_proxy("company-schema-discovery") as proxy:
        database_names = (
            [configured_db]
            if configured_db
            else [
                name for name in proxy.list_database_names()
                if name not in {"admin", "config", "local"}
            ]
        )
        collections = []

        for database_name in database_names:
            namespaces = proxy.list_collections(database_name)

            for namespace in namespaces[:safe_limit]:
                collection_name = namespace["name"]
                namespace_type = namespace.get("type", "collection")
                stats = {}

                if namespace_type == "collection":
                    stats = proxy.collection_stats(
                        database_name,
                        collection_name,
                    )

                collections.append({
                    "database": database_name,
                    "collection": collection_name,
                    "type": namespace_type,
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

    with get_company_mongo_read_proxy("company-schema-preview") as proxy:
        rows = proxy.find(
            database_name,
            collection_name,
            {},
            {"_id": 0},
            limit=safe_limit,
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

    with get_company_mongo_read_proxy("company-schema-inspection") as proxy:
        rows = proxy.find(
            database_name,
            collection_name,
            {},
            {"_id": 0},
            limit=safe_limit,
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

    with get_company_mongo_read_proxy("company-payload-inspection") as proxy:
        rows = proxy.find(
            database_name,
            collection_name,
            {payload_field: {"$exists": True}},
            {"_id": 0, payload_field: 1, "cnf": 1},
            limit=safe_limit,
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


def get_metric_value(metrics, names):
    accepted_names = {name.lower() for name in names}

    for metric in metrics:
        metric_name = str(metric.get("name") or "").lower()

        if metric_name in accepted_names:
            return metric.get("value")

    return None


def normalize_company_key(value):
    if value is None:
        return ""

    normalized = str(value).strip()

    if not normalized:
        return ""

    lowered = normalized.lower()

    for prefix in DEVICE_ID_PREFIXES:
        if lowered.startswith(prefix):
            return normalized[len(prefix):].lower()

    return lowered


def company_reference_id(value):
    if value is None:
        return ""

    if hasattr(value, "id"):
        return str(value.id)

    return str(value)


def company_aliases(*values):
    return {
        normalized
        for value in values
        if (normalized := normalize_company_key(value))
    }


def coerce_company_metric_value(value):
    if not isinstance(value, str):
        return value

    compact_value = value.strip()

    if not compact_value:
        return value

    try:
        if "." in compact_value:
            return float(compact_value)

        return int(compact_value)
    except ValueError:
        return value


def metric_catalog_units(rows):
    units_by_name = {}

    for row in rows:
        for metric in row.get("telemetry") or []:
            name = str(metric.get("telemetryName") or "").strip().lower()
            unit = str(metric.get("uom") or "").strip()

            if not name or not unit:
                continue

            units_by_name.setdefault(name, set()).add(unit)

    return {
        name: next(iter(units))
        for name, units in units_by_name.items()
        if len(units) == 1
    }


def metric_catalog_by_device(rows):
    catalog = {}

    for row in rows:
        aliases = company_aliases(row.get("_id"))
        telemetry = [
            {
                "name": str(metric.get("telemetryName") or "").strip(),
                "unit": str(metric.get("uom") or "").strip(),
                "type": metric.get("type"),
            }
            for metric in row.get("telemetry") or []
            if str(metric.get("telemetryName") or "").strip()
        ]

        if not telemetry:
            continue

        for alias in aliases:
            catalog[alias] = telemetry

    return catalog


def rule_filters_by_device(rules):
    filters_by_device = {}

    for rule in rules:
        action = rule.get("action") or {}
        filters = [
            filter_rule
            for filter_rule in rule.get("filters") or []
            if isinstance(filter_rule, dict) and filter_rule.get("field")
        ]

        if not filters:
            continue

        for raw_device_id in (
            rule.get("deviceIds") or action.get("deviceIds") or []
        ):
            for alias in company_aliases(raw_device_id):
                filters_by_device.setdefault(alias, []).extend(filters)

    return filters_by_device


def device_catalog_metrics(device, catalog):
    aliases = company_aliases(
        device.get("device_id"),
        device.get("device_name"),
        device.get("node_id"),
        *device.get("_aliases", set()),
    )

    for alias in aliases:
        if alias in catalog:
            return catalog[alias]

    return []


def device_rule_filters(device, filters_by_device):
    aliases = company_aliases(
        device.get("device_id"),
        device.get("device_name"),
        device.get("node_id"),
        *device.get("_aliases", set()),
    )
    filters = []

    for alias in aliases:
        filters.extend(filters_by_device.get(alias, []))

    return filters


def infer_unnamed_value_metrics(raw_metrics, device, catalog, filters_by_device):
    if len(raw_metrics) != 1:
        return raw_metrics

    metric = raw_metrics[0]

    if metric.get("name") != "value":
        return raw_metrics

    rule_filters = device_rule_filters(device, filters_by_device)

    if len(rule_filters) == 1:
        return [{
            **metric,
            "name": str(rule_filters[0].get("field")),
            "inferred_from": "datamgmt.RULE.filters",
            "rule_operator": rule_filters[0].get("operator"),
            "rule_threshold": rule_filters[0].get("value"),
        }]

    catalog_metrics = device_catalog_metrics(device, catalog)

    if len(catalog_metrics) == 1:
        return [{
            **metric,
            "name": catalog_metrics[0]["name"],
            "unit": catalog_metrics[0].get("unit", ""),
            "inferred_from": "datamgmt.DEVICE_TELEMETRY",
        }]

    return raw_metrics


def summarize_company_rule(rule):
    filters = [
        {
            "field": filter_rule.get("field"),
            "operator": filter_rule.get("operator"),
            "value": trim_value(filter_rule.get("value")),
            "data_type": filter_rule.get("dataType"),
        }
        for filter_rule in rule.get("filters") or []
        if isinstance(filter_rule, dict)
    ]
    action = rule.get("action") or {}

    return {
        "name": rule.get("name"),
        "status": rule.get("status"),
        "type": rule.get("type"),
        "target": rule.get("target"),
        "trigger_type": rule.get("triggerType"),
        "connection_status": rule.get("connectionStatus"),
        "device_ids": rule.get("deviceIds") or action.get("deviceIds") or [],
        "filters": filters,
        "action": {
            "type": action.get("type"),
            "notification_type": action.get("notificationType"),
            "interval_time": action.get("intervalTime"),
            "title": trim_value(action.get("title")),
            "has_content": bool(action.get("content")),
        },
        "mapping_status": (
            "filter_mapped_read_only"
            if filters or rule.get("connectionStatus") is not None
            else "catalog_only"
        ),
        "source": "datamgmt.RULE",
    }


def status_bucket(status):
    normalized = str(status or "").strip().lower()

    if normalized in CONNECTED_STATUS_VALUES:
        return "connected"

    if normalized in DISCONNECTED_STATUS_VALUES:
        return "disconnected"

    return "unknown"


def evaluate_threshold(value, evaluation):
    if value is None:
        return "not_evaluable"

    if "good_min" in evaluation and value >= evaluation["good_min"]:
        return "good"

    if "good_below" in evaluation and value < evaluation["good_below"]:
        return "good"

    if "good_max" in evaluation and value <= evaluation["good_max"]:
        return "good"

    if "critical_below" in evaluation and value < evaluation["critical_below"]:
        return "critical"

    if "critical_above" in evaluation and value > evaluation["critical_above"]:
        return "critical"

    if "warning_min" in evaluation and value >= evaluation["warning_min"]:
        return "warning"

    if "warning_max" in evaluation and value <= evaluation["warning_max"]:
        return "warning"

    return "unknown"


def company_db_kpi_rules():
    return [
        rule
        for rule in load_grafana_kpi_rules().get("rules", [])
        if rule.get("implementation_status") == "available_company_db"
    ]


def build_company_kpi_evaluations(model):
    devices = model.get("devices") or []
    total_devices = len(devices)
    connected_count = len([
        device for device in devices
        if status_bucket(device.get("status")) == "connected"
    ])
    disconnected_count = len([
        device for device in devices
        if status_bucket(device.get("status")) == "disconnected"
    ])
    unknown_count = max(0, total_devices - connected_count - disconnected_count)
    status_evidence_count = connected_count + disconnected_count
    content_count = model.get("content_instance_count", 0)
    invalid_payload_count = model.get("invalid_payload_count", 0)
    connected_rate = (
        round((connected_count / status_evidence_count) * 100, 2)
        if status_evidence_count
        else None
    )
    invalid_payload_rate = (
        round((invalid_payload_count / content_count) * 100, 2)
        if content_count
        else None
    )
    metrics = {
        "connected_devices_rate_percent": {
            "value": connected_rate,
            "evidence": {
                "connected_devices": connected_count,
                "disconnected_devices": disconnected_count,
                "unknown_status_devices": unknown_count,
                "status_evidence_devices": status_evidence_count,
                "total_devices": total_devices,
                "source": "devicemgmt.NODE + datamgmt.CIN.con.status",
            },
        },
        "invalid_payload_rate_percent": {
            "value": invalid_payload_rate,
            "evidence": {
                "invalid_payloads": invalid_payload_count,
                "content_instances_scanned": content_count,
                "parseable_payloads": model.get("parseable_payload_count", 0),
                "source": "datamgmt.CIN.con",
            },
        },
    }
    evaluations = []

    for rule in company_db_kpi_rules():
        evaluation = rule.get("evaluation") or {}
        metric_name = evaluation.get("metric")
        metric = metrics.get(metric_name)

        if not metric:
            continue

        value = metric.get("value")
        evaluations.append({
            "kpi": rule.get("kpi"),
            "tool": rule.get("tool"),
            "metric": metric_name,
            "unit": rule.get("unit"),
            "value": value,
            "status": evaluate_threshold(value, evaluation),
            "thresholds": {
                key: evaluation.get(key)
                for key in (
                    "good_min",
                    "good_below",
                    "good_max",
                    "warning_min",
                    "warning_max",
                    "critical_below",
                    "critical_above",
                )
                if key in evaluation
            },
            "implementation_status": rule.get("implementation_status"),
            "evidence": metric.get("evidence"),
            "source": "grafana_kpi_rules.json + company_mongodb",
        })

    return evaluations


def build_company_kpi_alerts(kpi_evaluations):
    alerts = []

    for evaluation in kpi_evaluations:
        status = evaluation.get("status")

        if status not in {"critical", "warning"}:
            continue

        alerts.append({
            "alert_id": f"kpi:{evaluation.get('metric')}",
            "title": evaluation.get("kpi"),
            "severity": status,
            "status": "active",
            "policy": "kpi_workbook_read_only",
            "official": True,
            "metric": evaluation.get("metric"),
            "value": evaluation.get("value"),
            "unit": evaluation.get("unit"),
            "thresholds": evaluation.get("thresholds"),
            "evidence": evaluation.get("evidence"),
            "source": evaluation.get("source"),
            "tool": evaluation.get("tool"),
        })

    critical_count = len([
        alert for alert in alerts
        if alert["severity"] == "critical"
    ])
    warning_count = len([
        alert for alert in alerts
        if alert["severity"] == "warning"
    ])

    return {
        "critical_count": critical_count,
        "warning_count": warning_count,
        "total_count": len(alerts),
        "rules_status": "kpi_workbook",
        "policy": "kpi_workbook_read_only",
        "official": True,
        "active_alerts": alerts,
        "message": (
            "Official alert view is populated from KPI workbook rules that are "
            "currently evaluable from the company DB. Device-level company "
            "RULE execution still requires confirmed operator semantics."
        ),
    }


def enrich_company_metrics(metrics, units):
    enriched = []

    for metric in metrics:
        name = str(metric.get("name") or "")

        if name.lower() in SEMANTIC_METRIC_NAMES:
            continue

        value = coerce_company_metric_value(metric.get("value"))
        enriched.append({
            **metric,
            "value": value,
            "type": describe_value_type(value),
            "unit": metric.get("unit") or units.get(name.lower(), ""),
        })

    return enriched


def company_device_record(node, child, identity=None):
    raw_id = child.get("_id") or child.get("rn") or child.get("dvnm")
    aliases = company_aliases(
        child.get("_id"),
        child.get("rn"),
        child.get("dvnm"),
    )

    return {
        "record_id": str(child.get("rn") or raw_id),
        "device_id": (
            str(raw_id)[4:]
            if str(raw_id).lower().startswith(("dvi-", "dvi_"))
            else str(raw_id)
        ),
        "device_name": child.get("dvnm") or child.get("rn") or raw_id,
        "status": "unknown",
        "status_source": "not_available",
        "timestamp": node.get("lt") or node.get("ct"),
        "company_record": True,
        "inventory_source": "devicemgmt.NODE",
        "node_id": node.get("rn"),
        "node_type": node.get("nty"),
        "category": child.get("dty") or node.get("category"),
        "connectivity": child.get("cnty"),
        "protocol": child.get("ptl"),
        "manufacturer": child.get("man"),
        "model": child.get("mod"),
        "firmware_version": child.get("fwv"),
        "software_version": child.get("swv"),
        "os_version": child.get("osv"),
        "identity_active": identity.get("active") if identity else None,
        "identity_category": identity.get("category") if identity else None,
        "tenant_name": node.get("tenantName"),
        "app_domain_name": node.get("appDomainName"),
        "parent_container": "",
        "content_format": None,
        "payload_summary": None,
        "metrics": [],
        "telemetry_record_count": 0,
        "rule_count": 0,
        "rules_status": "available_unmapped",
        "cpu_usage": None,
        "memory_usage": None,
        "heartbeat_delay": None,
        "_aliases": aliases,
        "_history": [],
        "_metric_timestamps": {},
    }


def resolve_company_device(alias_index, aliases):
    for alias in aliases:
        device = alias_index.get(alias)

        if device:
            return device

    return None


def load_company_device_read_model(
    proxy,
    cin_limit=DEFAULT_COMPANY_CIN_SCAN_LIMIT,
):
    safe_cin_limit = max(1, min(int(cin_limit), 1000))
    nodes = proxy.find(
        "devicemgmt",
        "NODE",
        {},
        {
            "_id": 0,
            "rn": 1,
            "ni": 1,
            "nty": 1,
            "category": 1,
            "ct": 1,
            "lt": 1,
            "tenantId": 1,
            "tenantName": 1,
            "appDomainId": 1,
            "appDomainName": 1,
            "childDeviceInfoEntities": 1,
        },
        limit=MAX_COMPANY_INVENTORY_RECORDS,
    )
    identities = proxy.find(
        "authorization",
        "IDENTITY",
        {},
        {
            "_id": 0,
            "name": 1,
            "userId": 1,
            "category": 1,
            "type": 1,
            "active": 1,
            "tenantId": 1,
        },
        limit=MAX_COMPANY_INVENTORY_RECORDS,
    )
    containers = proxy.find(
        "datamgmt",
        "CNT",
        {},
        {
            "_id": 1,
            "rn": 1,
            "pi": 1,
            "cr": 1,
            "parentContainer": 1,
        },
        limit=MAX_COMPANY_INVENTORY_RECORDS,
    )
    rules = proxy.find(
        "datamgmt",
        "RULE",
        {},
        {
            "_id": 0,
            "deviceIds": 1,
            "action": 1,
            "connectionStatus": 1,
            "filters": 1,
            "name": 1,
            "status": 1,
            "target": 1,
            "triggerType": 1,
            "type": 1,
        },
        limit=MAX_COMPANY_INVENTORY_RECORDS,
    )
    telemetry_catalog = proxy.find(
        "datamgmt",
        "DEVICE_TELEMETRY",
        {},
        {"_id": 1, "telemetry": 1},
        limit=MAX_COMPANY_INVENTORY_RECORDS,
    )
    content_instances = proxy.find(
        "datamgmt",
        "CIN",
        {},
        {
            "_id": 0,
            "rn": 1,
            "pi": 1,
            "parentContainer": 1,
            "ct": 1,
            "lt": 1,
            "cnf": 1,
            "con": 1,
            "tenantId": 1,
            "tenantName": 1,
            "appDomainId": 1,
            "appDomainName": 1,
        },
        sort=DEFAULT_COMPANY_CIN_SORT,
        limit=safe_cin_limit,
    )

    identities_by_alias = {}

    for identity in identities:
        for alias in company_aliases(
            identity.get("name"),
            identity.get("userId"),
        ):
            identities_by_alias.setdefault(alias, identity)

    devices = []
    alias_index = {}

    for node in nodes:
        for child in node.get("childDeviceInfoEntities") or []:
            identity = resolve_company_device(
                identities_by_alias,
                company_aliases(child.get("dvnm"), child.get("_id")),
            )
            device = company_device_record(node, child, identity)
            devices.append(device)

            for alias in device["_aliases"]:
                alias_index.setdefault(alias, device)

    containers_by_id = {
        company_reference_id(container.get("_id")): container
        for container in containers
    }
    containers_by_name = {
        str(container.get("rn")): container
        for container in containers
        if container.get("rn")
    }
    telemetry_container_ids_by_device = {}

    for container in containers:
        container_name = str(container.get("rn") or "").lower()

        if "telemetry" not in container_name:
            continue

        device = resolve_company_device(
            alias_index,
            company_aliases(
                container.get("pi"),
                container.get("cr"),
                container.get("parentContainer"),
            ),
        )

        if not device:
            continue

        telemetry_container_ids_by_device.setdefault(id(device), []).append(
            company_reference_id(container.get("_id"))
        )
        device.setdefault("_telemetry_container_ids", set()).add(
            company_reference_id(container.get("_id"))
        )

    seen_content_records = {
        row.get("rn") or f"{row.get('pi')}:{row.get('ct')}:{row.get('lt')}"
        for row in content_instances
    }
    cin_per_device_limit = max(
        1,
        min(
            int(os.getenv(
                "COMPANY_CIN_PER_DEVICE_LIMIT",
                str(DEFAULT_COMPANY_CIN_PER_DEVICE_LIMIT),
            )),
            100,
        ),
    )
    cin_projection = {
        "_id": 0,
        "rn": 1,
        "pi": 1,
        "parentContainer": 1,
        "ct": 1,
        "lt": 1,
        "cnf": 1,
        "con": 1,
        "tenantId": 1,
        "tenantName": 1,
        "appDomainId": 1,
        "appDomainName": 1,
    }

    for container_ids in telemetry_container_ids_by_device.values():
        for container_id in sorted(container_ids):
            if not container_id:
                continue

            for row in proxy.find(
                "datamgmt",
                "CIN",
                {"pi": container_id},
                cin_projection,
                sort=DEFAULT_COMPANY_CIN_SORT,
                limit=cin_per_device_limit,
            ):
                content_key = (
                    row.get("rn")
                    or f"{row.get('pi')}:{row.get('ct')}:{row.get('lt')}"
                )

                if content_key in seen_content_records:
                    continue

                seen_content_records.add(content_key)
                content_instances.append(row)

    units = metric_catalog_units(telemetry_catalog)
    catalog = metric_catalog_by_device(telemetry_catalog)
    filters_by_device = rule_filters_by_device(rules)
    unmapped_telemetry_count = 0
    command_record_count = 0
    invalid_payload_count = 0
    parseable_payload_count = 0
    telemetry_payload_count = 0

    for row in content_instances:
        parsed_payload = parse_payload_value(row.get("con"))

        if not isinstance(parsed_payload, dict):
            invalid_payload_count += 1
            continue

        parseable_payload_count += 1
        is_command_record = bool(
            parsed_payload.get("commandId")
            or parsed_payload.get("commandType")
        )

        if is_command_record:
            command_record_count += 1
            continue

        telemetry_payload_count += 1

        payload_aliases = company_aliases(
            parsed_payload.get("deviceId"),
            parsed_payload.get("deviceName"),
            parsed_payload.get("id"),
            parsed_payload.get("name"),
        )
        device = resolve_company_device(alias_index, payload_aliases)
        parent_reference = (
            company_reference_id(row.get("parentContainer"))
            or str(row.get("pi") or "")
        )
        container = (
            containers_by_id.get(parent_reference)
            or containers_by_name.get(parent_reference)
        )

        if not device and container:
            device = resolve_company_device(
                alias_index,
                company_aliases(
                    container.get("pi"),
                    container.get("cr"),
                    container.get("rn"),
                ),
            )

        raw_metrics = extract_display_metrics(row.get("con"))
        if device:
            raw_metrics = infer_unnamed_value_metrics(
                raw_metrics,
                device,
                catalog,
                filters_by_device,
            )
        metrics = enrich_company_metrics(raw_metrics, units)
        payload_status = get_metric_value(
            raw_metrics,
            {"status", "connectionStatus"},
        )
        has_direct_device_identity = bool(
            parsed_payload.get("deviceId")
            or parsed_payload.get("deviceName")
        )
        if not device and has_direct_device_identity:
            device_id = (
                parsed_payload.get("deviceId")
                or parsed_payload.get("deviceName")
            )
            device = {
                "record_id": str(row.get("rn") or device_id),
                "device_id": str(device_id),
                "device_name": (
                    parsed_payload.get("deviceName")
                    or parsed_payload.get("deviceId")
                ),
                "status": "unknown",
                "status_source": "not_available",
                "timestamp": row.get("lt") or row.get("ct"),
                "company_record": True,
                "inventory_source": "datamgmt.CIN",
                "node_id": None,
                "node_type": None,
                "category": None,
                "connectivity": None,
                "protocol": None,
                "manufacturer": None,
                "model": None,
                "firmware_version": None,
                "software_version": None,
                "os_version": None,
                "identity_active": None,
                "identity_category": None,
                "tenant_name": row.get("tenantName"),
                "app_domain_name": row.get("appDomainName"),
                "parent_container": str(row.get("pi") or ""),
                "content_format": row.get("cnf"),
                "payload_summary": summarize_payload(row.get("con")),
                "metrics": [],
                "telemetry_record_count": 0,
                "rule_count": 0,
                "rules_status": "available_unmapped",
                "cpu_usage": None,
                "memory_usage": None,
                "heartbeat_delay": None,
                "_aliases": payload_aliases,
                "_history": [],
                "_metric_timestamps": {},
            }
            devices.append(device)

            for alias in payload_aliases:
                alias_index.setdefault(alias, device)

        if not device:
            if metrics:
                unmapped_telemetry_count += 1

            continue

        timestamp = row.get("lt") or row.get("ct")
        device["telemetry_record_count"] += 1
        device["_history"].append({
            "record_id": row.get("rn"),
            "timestamp": timestamp,
            "status": payload_status,
            "metrics": metrics,
            "parent_container": str(row.get("pi") or ""),
        })

        if timestamp and (
            not device.get("timestamp")
            or int(timestamp) > int(device["timestamp"])
        ):
            device["timestamp"] = timestamp
            device["record_id"] = str(row.get("rn") or device["record_id"])
            device["parent_container"] = str(row.get("pi") or "")
            device["content_format"] = row.get("cnf")
            device["payload_summary"] = summarize_payload(row.get("con"))
            device["tenant_name"] = (
                row.get("tenantName") or device.get("tenant_name")
            )
            device["app_domain_name"] = (
                row.get("appDomainName") or device.get("app_domain_name")
            )

        if payload_status is not None and device["status_source"] == "not_available":
            device["status"] = str(payload_status)
            device["status_source"] = "payload"

        for metric in metrics:
            metric_name = metric.get("name")

            if not metric_name:
                continue

            previous_timestamp = device["_metric_timestamps"].get(metric_name)

            if previous_timestamp is not None and int(previous_timestamp) >= int(timestamp or 0):
                continue

            device["_metric_timestamps"][metric_name] = timestamp or 0
            existing_index = next(
                (
                    index
                    for index, existing in enumerate(device["metrics"])
                    if existing.get("name") == metric_name
                ),
                None,
            )

            if existing_index is None:
                device["metrics"].append(metric)
            else:
                device["metrics"][existing_index] = metric

        device["metrics"] = device["metrics"][:MAX_DISPLAY_METRICS]

    for rule in rules:
        matched_devices = set()

        action = rule.get("action") or {}

        for raw_device_id in (
            rule.get("deviceIds") or action.get("deviceIds") or []
        ):
            device = resolve_company_device(
                alias_index,
                company_aliases(raw_device_id),
            )

            if device and id(device) not in matched_devices:
                device["rule_count"] += 1
                matched_devices.add(id(device))

    for device in devices:
        device["_history"].sort(
            key=lambda item: int(item.get("timestamp") or 0),
        )
        device.pop("_metric_timestamps", None)
        device.pop("_telemetry_container_ids", None)

    return {
        "devices": devices,
        "inventory_node_count": len(nodes),
        "identity_count": len(identities),
        "container_count": len(containers),
        "rule_count": len(rules),
        "rules": [
            summarize_company_rule(rule)
            for rule in rules
        ],
        "telemetry_catalog_count": len(telemetry_catalog),
        "content_instance_count": len(content_instances),
        "invalid_payload_count": invalid_payload_count,
        "parseable_payload_count": parseable_payload_count,
        "telemetry_payload_count": telemetry_payload_count,
        "unmapped_telemetry_count": unmapped_telemetry_count,
        "command_record_count": command_record_count,
    }


def build_company_read_model_audit_plan(
    actor,
    cin_limit=DEFAULT_COMPANY_CIN_SCAN_LIMIT,
):
    safe_cin_limit = max(1, min(int(cin_limit), 1000))

    def event(database_name, collection_name, projection, limit, sort=None):
        return {
            "actor": actor,
            "operation": "find",
            "namespace": f"{database_name}.{collection_name}",
            "query": {},
            "projection": projection,
            "sort": sort,
            "requested_limit": limit,
            "effective_limit": max(1, min(int(limit), 1000)),
            "max_time_ms": None,
            "allowed_namespaces_enforced": True,
            "credentials_redacted": True,
            "mutating": False,
            "audit_source": "read_plan_fallback",
        }

    return [
        event(
            "devicemgmt",
            "NODE",
            {
                "_id": 0,
                "rn": 1,
                "ni": 1,
                "nty": 1,
                "category": 1,
                "ct": 1,
                "lt": 1,
                "tenantId": 1,
                "tenantName": 1,
                "appDomainId": 1,
                "appDomainName": 1,
                "childDeviceInfoEntities": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        event(
            "authorization",
            "IDENTITY",
            {
                "_id": 0,
                "name": 1,
                "userId": 1,
                "category": 1,
                "type": 1,
                "active": 1,
                "tenantId": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        event(
            "datamgmt",
            "CNT",
            {
                "_id": 1,
                "rn": 1,
                "pi": 1,
                "cr": 1,
                "parentContainer": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        event(
            "datamgmt",
            "RULE",
            {
                "_id": 0,
                "deviceIds": 1,
                "action": 1,
                "connectionStatus": 1,
                "filters": 1,
                "name": 1,
                "status": 1,
                "target": 1,
                "triggerType": 1,
                "type": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        event(
            "datamgmt",
            "DEVICE_TELEMETRY",
            {"_id": 0, "telemetry": 1},
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        event(
            "datamgmt",
            "CIN",
            {
                "_id": 0,
                "rn": 1,
                "pi": 1,
                "parentContainer": 1,
                "ct": 1,
                "lt": 1,
                "cnf": 1,
                "con": 1,
                "tenantId": 1,
                "tenantName": 1,
                "appDomainId": 1,
                "appDomainName": 1,
            },
            safe_cin_limit,
            sort=DEFAULT_COMPANY_CIN_SORT,
        ),
    ]


def serialize_company_device(device):
    return {
        key: value
        for key, value in device.items()
        if not key.startswith("_")
    }


def list_company_operational_records(limit=DEFAULT_OPERATIONAL_RECORD_LIMIT):
    with get_company_mongo_read_proxy("company-operational-read") as proxy:
        model = load_company_device_read_model(
            proxy,
            max(int(limit), DEFAULT_COMPANY_CIN_SCAN_LIMIT),
        )

    return [
        serialize_company_device(device)
        for device in model["devices"]
    ][:max(1, min(int(limit), 100))]


def get_company_device_history(device_id, limit=DEFAULT_OPERATIONAL_RECORD_LIMIT):
    safe_limit = max(1, min(int(limit), 100))

    with get_company_mongo_read_proxy("company-device-history") as proxy:
        model = load_company_device_read_model(proxy)

    target_alias = normalize_company_key(device_id)

    for device in model["devices"]:
        if target_alias not in device.get("_aliases", set()):
            continue

        return {
            "source": "company_mongodb",
            "device_id": device.get("device_id"),
            "device_name": device.get("device_name"),
            "history": device.get("_history", [])[-safe_limit:],
        }

    return {
        "source": "company_mongodb",
        "device_id": device_id,
        "device_name": None,
        "history": [],
    }


def get_company_operational_payload(
    limit=DEFAULT_OPERATIONAL_RECORD_LIMIT,
    proxy_actor="company-api",
):
    if company_db_type() != "mongodb":
        return simulator_fallback_snapshot(
            "Company MongoDB URL is not configured."
        )

    try:
        with get_company_mongo_read_proxy(proxy_actor) as proxy:
            model = load_company_device_read_model(
                proxy,
                max(int(limit), DEFAULT_COMPANY_CIN_SCAN_LIMIT),
            )
            db_audit = proxy.get_audit_events()
    except Exception as exc:
        return simulator_fallback_snapshot(
            f"Company MongoDB read failed: {exc}"
        )

    db_read_plan = build_company_read_model_audit_plan(
        proxy_actor,
        max(int(limit), DEFAULT_COMPANY_CIN_SCAN_LIMIT),
    )
    db_audit_status = "runtime_audit_available" if db_audit else "missing_runtime_audit"

    records = [
        serialize_company_device(device)
        for device in model["devices"]
    ][:max(1, min(int(limit), 100))]
    alerts = evaluate_company_poc_rules(records)
    company_rule_mappings = model.get("rules") or []
    kpi_evaluations = build_company_kpi_evaluations(model)
    official_alerts = build_company_kpi_alerts(kpi_evaluations)
    official_rules_status = (
        "discovered_mapped_read_only"
        if company_rule_mappings
        else "not_discovered"
    )

    return {
        "source": "company_mongodb",
        "provenance": {
            "collections": [
                "devicemgmt.NODE",
                "authorization.IDENTITY",
                "datamgmt.CNT",
                "datamgmt.CIN",
                "datamgmt.DEVICE_TELEMETRY",
                "datamgmt.RULE",
            ],
            "query": "bounded device inventory and recent telemetry join",
            "payload_field": "con",
            "device_inventory_field": "NODE.childDeviceInfoEntities",
            "identity_join": "device name",
            "telemetry_join": "payload identity or CIN/CNT parent ownership",
            "rule_mapping": "datamgmt.RULE filters/action/deviceIds/status",
            "kpi_mapping": "grafana_kpi_rules.json available_company_db metrics",
            "cin_scan_limit": max(
                int(limit),
                DEFAULT_COMPANY_CIN_SCAN_LIMIT,
            ),
            "db_audit": db_audit,
            "db_read_plan": db_read_plan,
            "db_audit_status": db_audit_status,
        },
        "db_audit": db_audit,
        "db_read_plan": db_read_plan,
        "db_audit_status": db_audit_status,
        "selected_source": "company",
        "active_source": "company_mongodb",
        "rules_status": "provisional_poc",
        "official_rules_status": official_rules_status,
        "rules_message": (
            "PoC fallback alerts are active for the demo. Company DB rules "
            "are mapped as read-only catalog/filter evidence; official alert "
            "execution still requires confirmed enum/operator semantics."
        ),
        "summary": {
            "device_count": len(records),
            "inventory_node_count": model["inventory_node_count"],
            "identity_count": model["identity_count"],
            "container_count": model["container_count"],
            "rule_count": model["rule_count"],
            "telemetry_catalog_count": model["telemetry_catalog_count"],
            "content_instance_count": model["content_instance_count"],
            "invalid_payload_count": model["invalid_payload_count"],
            "parseable_payload_count": model["parseable_payload_count"],
            "telemetry_payload_count": model["telemetry_payload_count"],
            "unmapped_telemetry_count": model["unmapped_telemetry_count"],
            "command_record_count": model["command_record_count"],
        },
        "devices": records,
        "alerts": alerts,
        "official_alerts": official_alerts,
        "company_rule_mappings": company_rule_mappings,
        "kpi_evaluations": kpi_evaluations,
    }


def get_company_agent_context(limit=DEFAULT_OPERATIONAL_RECORD_LIMIT):
    payload = get_company_operational_payload(
        limit,
        proxy_actor="company-llm-tools",
    )

    if payload.get("source") != "company_mongodb":
        return payload

    records = payload.get("devices") or []
    samples = []

    for record in records:
        metrics = record.get("metrics") or []
        samples.append({
            "record_id": record.get("record_id"),
            "record_type": "unified company device",
            "device_id": record.get("device_id"),
            "device_name": record.get("device_name"),
            "latest_payload_status": record.get("status"),
            "status_source": record.get("status_source"),
            "inventory_source": record.get("inventory_source"),
            "node_id": record.get("node_id"),
            "category": record.get("category"),
            "model": record.get("model"),
            "protocol": record.get("protocol"),
            "parent_container": record.get("parent_container"),
            "timestamp": record.get("timestamp"),
            "tenant_name": record.get("tenant_name"),
            "app_domain_name": record.get("app_domain_name"),
            "telemetry_record_count": record.get("telemetry_record_count"),
            "rule_count": record.get("rule_count"),
            "metric_names": [
                metric.get("name")
                for metric in metrics
                if metric.get("name")
            ],
            "metrics": metrics,
        })

        if len(samples) >= MAX_AGENT_SAMPLE_RECORDS:
            break

    return {
        "source": payload["source"],
        "provenance": payload.get("provenance"),
        "db_audit": payload.get("db_audit"),
        "db_read_plan": payload.get("db_read_plan"),
        "db_audit_status": payload.get("db_audit_status"),
        "summary": payload.get("summary"),
        "alerts": {
            **{
                key: payload.get("alerts", {}).get(key)
                for key in (
                    "critical_count",
                    "warning_count",
                    "total_count",
                    "rules_status",
                    "policy",
                    "official",
                    "ruleset_version",
                    "message",
                )
            },
            "samples": (payload.get("alerts", {}).get("active_alerts") or [])[
                :MAX_AGENT_SAMPLE_RECORDS
            ],
        },
        "record_count": len(records),
        "distinct_device_count": len(records),
        "record_type": "unified company devices",
        "rules_status": payload.get("rules_status"),
        "rules_message": payload.get("rules_message"),
        "official_rules_status": payload.get("official_rules_status"),
        "company_rule_mappings": (
            payload.get("company_rule_mappings") or []
        )[:MAX_AGENT_SAMPLE_RECORDS],
        "kpi_evaluations": payload.get("kpi_evaluations") or [],
        "classification_status": "provisional_poc_rules_active",
        "interpretation_notes": [
            "Device inventory is read from devicemgmt.NODE child device entities and augmented with authorization identity metadata.",
            "Latest status and telemetry are joined from datamgmt.CIN using payload identity or CIN/CNT ownership.",
            "Payload status is a raw device-reported value, not an alert severity.",
            "Displayed alerts come from provisional PoC rules, not from official company or Grafana evaluation.",
            "Company rules from datamgmt.RULE are mapped as read-only filter/action evidence; official execution semantics still need confirmation.",
            "Company DB KPI evaluations are computed only for KPI workbook rules marked available_company_db.",
            "Unmapped telemetry is reported separately and is never assigned to a device by guesswork.",
        ],
        "sample_records": samples,
    }


def compact_company_device(device):
    return {
        "device_id": device.get("device_id"),
        "device_name": device.get("device_name"),
        "status": device.get("status"),
        "status_source": device.get("status_source"),
        "node_id": device.get("node_id"),
        "category": device.get("category"),
        "manufacturer": device.get("manufacturer"),
        "model": device.get("model"),
        "protocol": device.get("protocol"),
        "timestamp": device.get("timestamp"),
        "telemetry_record_count": device.get("telemetry_record_count"),
        "rule_count": device.get("rule_count"),
        "metrics": device.get("metrics"),
    }


def get_company_inventory_context(limit=MAX_AGENT_SAMPLE_RECORDS):
    payload = get_company_operational_payload(
        proxy_actor="company-llm-tools",
    )

    if payload.get("source") != "company_mongodb":
        return payload

    devices = payload.get("devices") or []
    inventory_devices = [
        device for device in devices
        if device.get("inventory_source") == "devicemgmt.NODE"
    ]
    telemetry_only_devices = [
        device for device in devices
        if device.get("inventory_source") == "datamgmt.CIN"
    ]

    return {
        "source": payload["source"],
        "tool": "get_company_inventory",
        "db_audit": payload.get("db_audit"),
        "db_read_plan": payload.get("db_read_plan"),
        "db_audit_status": payload.get("db_audit_status"),
        "summary": payload.get("summary"),
        "inventory_device_count": len(inventory_devices),
        "telemetry_only_device_count": len(telemetry_only_devices),
        "samples": [
            compact_company_device(device)
            for device in inventory_devices[:max(1, min(int(limit), 10))]
        ],
        "note": (
            "Inventory comes from devicemgmt.NODE. Telemetry-only identities "
            "are retained separately rather than being silently discarded."
        ),
    }


def get_company_telemetry_coverage_context(limit=MAX_AGENT_SAMPLE_RECORDS):
    payload = get_company_operational_payload(
        proxy_actor="company-llm-tools",
    )

    if payload.get("source") != "company_mongodb":
        return payload

    devices = payload.get("devices") or []
    with_telemetry = [
        device for device in devices
        if device.get("telemetry_record_count")
    ]
    without_telemetry = [
        device for device in devices
        if not device.get("telemetry_record_count")
    ]
    metric_coverage = {}

    for device in with_telemetry:
        for metric in device.get("metrics") or []:
            name = metric.get("name")

            if name:
                metric_coverage[name] = metric_coverage.get(name, 0) + 1

    return {
        "source": payload["source"],
        "tool": "get_company_telemetry_coverage",
        "db_audit": payload.get("db_audit"),
        "db_read_plan": payload.get("db_read_plan"),
        "db_audit_status": payload.get("db_audit_status"),
        "device_count": len(devices),
        "devices_with_telemetry": len(with_telemetry),
        "inventory_only_devices": len(without_telemetry),
        "unmapped_telemetry_count": payload.get("summary", {}).get(
            "unmapped_telemetry_count",
            0,
        ),
        "top_metric_fields": [
            {"name": name, "device_count": count}
            for name, count in sorted(
                metric_coverage.items(),
                key=lambda item: (-item[1], item[0]),
            )[:10]
        ],
        "sample_devices_with_telemetry": [
            compact_company_device(device)
            for device in with_telemetry[:max(1, min(int(limit), 10))]
        ],
    }


def get_company_provisional_alert_context(limit=MAX_AGENT_SAMPLE_RECORDS):
    payload = get_company_operational_payload(
        proxy_actor="company-llm-tools",
    )

    if payload.get("source") != "company_mongodb":
        return payload

    alerts = payload.get("alerts") or {}
    return {
        "source": payload["source"],
        "tool": "get_company_provisional_alerts",
        "db_audit": payload.get("db_audit"),
        "db_read_plan": payload.get("db_read_plan"),
        "db_audit_status": payload.get("db_audit_status"),
        "rules_status": payload.get("rules_status"),
        "official_rules_status": payload.get("official_rules_status"),
        "critical_count": alerts.get("critical_count", 0),
        "warning_count": alerts.get("warning_count", 0),
        "total_count": alerts.get("total_count", 0),
        "ruleset_version": alerts.get("ruleset_version"),
        "official": False,
        "alerts": (alerts.get("active_alerts") or [])[
            :max(1, min(int(limit), 10))
        ],
        "disclaimer": alerts.get("message"),
    }


def get_company_rule_readiness_context():
    payload = get_company_operational_payload(
        proxy_actor="company-llm-tools",
    )

    if payload.get("source") != "company_mongodb":
        return payload

    return {
        "source": payload["source"],
        "tool": "get_company_rule_readiness",
        "db_audit": payload.get("db_audit"),
        "db_read_plan": payload.get("db_read_plan"),
        "db_audit_status": payload.get("db_audit_status"),
        "company_rules_discovered": payload.get("summary", {}).get(
            "rule_count",
            0,
        ),
        "official_rules_status": payload.get("official_rules_status"),
        "company_rule_mappings": payload.get("company_rule_mappings") or [],
        "kpi_evaluations": payload.get("kpi_evaluations") or [],
        "mapped_kpi_count": len(payload.get("kpi_evaluations") or []),
        "poc_rules": get_company_poc_rule_catalog(),
        "next_integration": (
            "Confirm datamgmt.RULE enum/operator semantics and connect the "
            "authoritative Grafana alert source before promoting PoC alerts."
        ),
    }


def get_company_disconnected_context(limit=MAX_AGENT_SAMPLE_RECORDS):
    payload = get_company_operational_payload(
        proxy_actor="company-llm-tools",
    )

    if payload.get("source") != "company_mongodb":
        return payload

    disconnected = [
        compact_company_device(device)
        for device in payload.get("devices") or []
        if str(device.get("status") or "").lower() in {
            "disconnected",
            "offline",
        }
    ]

    return {
        "source": payload["source"],
        "tool": "get_company_disconnected_devices",
        "db_audit": payload.get("db_audit"),
        "db_read_plan": payload.get("db_read_plan"),
        "db_audit_status": payload.get("db_audit_status"),
        "count": len(disconnected),
        "devices": disconnected[:max(1, min(int(limit), 10))],
        "classification": "raw_device_status",
        "note": (
            "Disconnected status is device-reported evidence. Critical alert "
            "labels shown by the PoC come from provisional local rules."
        ),
    }


def get_company_device_context(identifier):
    payload = get_company_operational_payload(
        proxy_actor="company-llm-tools",
    )

    if payload.get("source") != "company_mongodb":
        return payload

    target = normalize_company_key(identifier)
    matches = []

    for device in payload.get("devices") or []:
        aliases = company_aliases(
            device.get("device_id"),
            device.get("device_name"),
            device.get("node_id"),
        )

        if target in aliases:
            matches.append(compact_company_device(device))

    return {
        "source": payload["source"],
        "tool": "get_company_device",
        "db_audit": payload.get("db_audit"),
        "db_read_plan": payload.get("db_read_plan"),
        "db_audit_status": payload.get("db_audit_status"),
        "query": identifier,
        "match_count": len(matches),
        "devices": matches[:MAX_AGENT_SAMPLE_RECORDS],
        "alerts": [
            alert
            for alert in payload.get("alerts", {}).get("active_alerts") or []
            if normalize_company_key(alert.get("device_id")) == target
        ][:MAX_AGENT_SAMPLE_RECORDS],
    }


def compact_resource_document(document):
    if not isinstance(document, dict):
        return document

    compact = {}

    for key in (
        "_id",
        "rn",
        "ri",
        "pi",
        "aei",
        "api",
        "rr",
        "cr",
        "ct",
        "lt",
        "parentContainer",
        "cnf",
        "con",
        "nu",
        "enc",
        "poa",
        "deviceId",
        "deviceName",
        "name",
        "userId",
        "category",
        "type",
        "active",
        "tenantId",
        "tenantName",
        "appDomainId",
        "appDomainName",
        "resourceId",
        "resourceUri",
        "targetUri",
    ):
        if key in document:
            compact[key] = trim_document(document.get(key))

    return compact or trim_document(document)


def resource_matches_identifier(document, identifier):
    if not identifier:
        return True

    target = normalize_company_key(identifier)

    for value in document.values():
        if isinstance(value, (dict, list)):
            continue

        if target and target in normalize_company_key(value):
            return True

    return False


def document_reference_values(document):
    values = set()

    if not isinstance(document, dict):
        return values

    for key in (
        "_id",
        "rn",
        "ri",
        "pi",
        "aei",
        "cr",
        "parentContainer",
        "resourceId",
        "resourceUri",
        "targetUri",
        "name",
        "userId",
    ):
        value = document.get(key)

        if value is None:
            continue

        values.add(company_reference_id(value))
        normalized = normalize_company_key(value)

        if normalized:
            values.add(normalized)

    return {value for value in values if value}


def cin_matches_identifier(row, identifier):
    if resource_matches_identifier(row, identifier):
        return True

    parsed_payload = parse_payload_value(row.get("con"))

    if not isinstance(parsed_payload, dict):
        return False

    target = normalize_company_key(identifier)
    aliases = company_aliases(
        parsed_payload.get("deviceId"),
        parsed_payload.get("deviceName"),
        parsed_payload.get("id"),
        parsed_payload.get("name"),
    )
    return target in aliases


def references_any(document, references):
    if not references:
        return False

    document_refs = document_reference_values(document)
    normalized_references = {
        normalize_company_key(reference) or str(reference)
        for reference in references
        if reference
    }

    for value in document_refs:
        normalized_value = normalize_company_key(value) or str(value)

        if value in references or normalized_value in normalized_references:
            return True

    return False


def related_onem2m_rows(raw_rows, identifier):
    if not identifier:
        return {
            label: list(rows)
            for label, rows in raw_rows.items()
        }

    matched = {
        label: [
            row for row in rows
            if resource_matches_identifier(row, identifier)
        ]
        for label, rows in raw_rows.items()
    }
    matched["CIN"] = [
        row for row in raw_rows.get("CIN", [])
        if cin_matches_identifier(row, identifier)
    ]

    related_refs = set()

    for row in matched.get("IDENTITY", []):
        related_refs.update(document_reference_values(row))

    for row in matched.get("CIN", []):
        related_refs.update(document_reference_values(row))

    for row in raw_rows.get("CNT", []):
        if row in matched.get("CNT", []) or references_any(row, related_refs):
            matched.setdefault("CNT", []).append(row)
            related_refs.update(document_reference_values(row))

    for row in raw_rows.get("AE", []):
        if row in matched.get("AE", []) or references_any(row, related_refs):
            matched.setdefault("AE", []).append(row)
            related_refs.update(document_reference_values(row))

    for row in raw_rows.get("SUBSCRIPTION", []):
        if (
            row in matched.get("SUBSCRIPTION", [])
            or references_any(row, related_refs)
        ):
            matched.setdefault("SUBSCRIPTION", []).append(row)
            related_refs.update(document_reference_values(row))

    for row in raw_rows.get("URI_MAPPER", []):
        if row in matched.get("URI_MAPPER", []) or references_any(row, related_refs):
            matched.setdefault("URI_MAPPER", []).append(row)

    deduped = {}

    for label, rows in matched.items():
        seen = set()
        deduped[label] = []

        for row in rows:
            key = tuple(sorted(document_reference_values(row))) or (id(row),)

            if key in seen:
                continue

            seen.add(key)
            deduped[label].append(row)

    return deduped


def read_onem2m_resource_sets(proxy, identifier=None):
    resource_specs = [
        (
            "IDENTITY",
            "authorization",
            "IDENTITY",
            {
                "_id": 0,
                "name": 1,
                "userId": 1,
                "category": 1,
                "type": 1,
                "active": 1,
                "tenantId": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        (
            "AE",
            "subNNotif",
            "AE",
            {
                "_id": 1,
                "rn": 1,
                "ri": 1,
                "aei": 1,
                "api": 1,
                "rr": 1,
                "poa": 1,
                "ct": 1,
                "lt": 1,
                "tenantId": 1,
                "appDomainId": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        (
            "CNT",
            "datamgmt",
            "CNT",
            {
                "_id": 1,
                "rn": 1,
                "pi": 1,
                "cr": 1,
                "parentContainer": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        (
            "CIN",
            "datamgmt",
            "CIN",
            {
                "_id": 0,
                "rn": 1,
                "pi": 1,
                "parentContainer": 1,
                "ct": 1,
                "lt": 1,
                "cnf": 1,
                "con": 1,
                "tenantId": 1,
                "tenantName": 1,
                "appDomainId": 1,
                "appDomainName": 1,
            },
            DEFAULT_COMPANY_CIN_SCAN_LIMIT,
        ),
        (
            "SUBSCRIPTION",
            "subNNotif",
            "SUB",
            {
                "_id": 1,
                "rn": 1,
                "ri": 1,
                "pi": 1,
                "nu": 1,
                "enc": 1,
                "ct": 1,
                "lt": 1,
                "tenantId": 1,
                "appDomainId": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
        (
            "URI_MAPPER",
            "orchestration",
            "URI_MAPPER",
            {
                "_id": 1,
                "rn": 1,
                "ri": 1,
                "resourceId": 1,
                "resourceUri": 1,
                "targetUri": 1,
                "ct": 1,
                "lt": 1,
                "tenantId": 1,
                "appDomainId": 1,
            },
            MAX_COMPANY_INVENTORY_RECORDS,
        ),
    ]
    raw_rows = {}
    resource_sets = {}

    for label, database_name, collection_name, projection, limit in resource_specs:
        sort = DEFAULT_COMPANY_CIN_SORT if label == "CIN" else None
        rows = proxy.find(
            database_name,
            collection_name,
            {},
            projection,
            sort=sort,
            limit=limit,
        )
        raw_rows[label] = rows

    direct_by_label = {
        label: [
            row for row in rows
            if resource_matches_identifier(row, identifier)
        ]
        for label, rows in raw_rows.items()
    }
    direct_by_label["CIN"] = [
        row for row in raw_rows.get("CIN", [])
        if cin_matches_identifier(row, identifier)
    ]
    matched_by_label = related_onem2m_rows(raw_rows, identifier)

    for label, database_name, collection_name, _, _ in resource_specs:
        rows = raw_rows.get(label, [])
        matched_rows = matched_by_label.get(label, [])
        direct_rows = direct_by_label.get(label, [])
        command_rows = []
        telemetry_rows = []

        if label == "CIN":
            for row in matched_rows:
                payload = parse_payload_value(row.get("con"))
                parent = str(
                    row.get("pi") or row.get("parentContainer") or ""
                ).lower()

                if is_command_payload(payload) or "command" in parent:
                    command_rows.append(row)
                elif isinstance(payload, dict) and (
                    "telemetry" in parent or extract_display_metrics(row.get("con"))
                ):
                    telemetry_rows.append(row)
        elif label == "CNT":
            for row in matched_rows:
                resource_name = str(
                    row.get("rn") or row.get("pi") or row.get("parentContainer") or ""
                ).lower()

                if "command" in resource_name:
                    command_rows.append(row)
                if "telemetry" in resource_name:
                    telemetry_rows.append(row)

        resource_sets[label] = {
            "namespace": f"{database_name}.{collection_name}",
            "count": len(rows),
            "matched_count": len(matched_rows),
            "direct_match_count": len(direct_rows),
            "related_match_count": max(0, len(matched_rows) - len(direct_rows)),
            "samples": [
                compact_resource_document(row)
                for row in matched_rows[:ONEM2M_RESOURCE_SAMPLE_LIMIT]
            ],
        }

        if label in {"CNT", "CIN"}:
            resource_sets[label]["command_samples"] = [
                compact_resource_document(row)
                for row in command_rows[:ONEM2M_RESOURCE_SAMPLE_LIMIT]
            ]
            resource_sets[label]["telemetry_samples"] = [
                compact_resource_document(row)
                for row in telemetry_rows[:ONEM2M_RESOURCE_SAMPLE_LIMIT]
            ]
            resource_sets[label]["command_count"] = len(command_rows)
            resource_sets[label]["telemetry_count"] = len(telemetry_rows)

    return resource_sets


def is_command_payload(payload):
    if not isinstance(payload, dict):
        return False

    keys = {str(key).lower() for key in payload.keys()}
    return bool({"commandid", "commandtype", "command", "cmd"} & keys)


def command_like_records(resource_sets):
    return resource_sets.get("CIN", {}).get("command_samples") or []


def telemetry_like_records(resource_sets):
    return resource_sets.get("CIN", {}).get("telemetry_samples") or []


def get_company_onem2m_device_resource_context(
    device_id=None,
    limit=MAX_AGENT_SAMPLE_RECORDS,
):
    if company_db_type() != "mongodb":
        return simulator_fallback_snapshot(
            "Company MongoDB URL is not configured."
        )

    try:
        with get_company_mongo_read_proxy("company-llm-tools") as proxy:
            model = load_company_device_read_model(proxy)
            resource_sets = read_onem2m_resource_sets(proxy, device_id)
            db_audit = proxy.get_audit_events()
    except Exception as exc:
        return simulator_fallback_snapshot(
            f"Company MongoDB read failed: {exc}"
        )

    devices = [serialize_company_device(device) for device in model["devices"]]
    target = normalize_company_key(device_id)

    if target:
        matched_devices = [
            compact_company_device(device)
            for device in devices
            if target in company_aliases(
                device.get("device_id"),
                device.get("device_name"),
                device.get("node_id"),
            )
        ]
    else:
        matched_devices = [
            compact_company_device(device)
            for device in devices[:max(1, min(int(limit), 10))]
        ]

    resource_summary = {
        label: {
            "namespace": resource.get("namespace"),
            "count": resource.get("count"),
            "matched_count": resource.get("matched_count"),
            "direct_match_count": resource.get("direct_match_count"),
            "related_match_count": resource.get("related_match_count"),
            "present": resource.get("matched_count", 0) > 0,
            "command_count": resource.get("command_count"),
            "telemetry_count": resource.get("telemetry_count"),
            "samples": resource.get("samples", [])[
                :max(1, min(int(limit), ONEM2M_RESOURCE_SAMPLE_LIMIT))
            ],
        }
        for label, resource in resource_sets.items()
    }

    return {
        "source": "company_mongodb",
        "tool": "get_company_onem2m_device_resources",
        "db_audit": db_audit,
        "db_audit_status": (
            "runtime_audit_available" if db_audit else "missing_runtime_audit"
        ),
        "query_device_id": device_id,
        "device_match_count": len(matched_devices),
        "devices": matched_devices[:max(1, min(int(limit), 10))],
        "resource_summary": resource_summary,
        "required_resources": [
            "IDENTITY",
            "AE",
            "CNT",
            "CIN",
            "SUBSCRIPTION",
            "URI_MAPPER",
        ],
        "summary": {
            "device_count": len(devices),
            "inventory_node_count": model["inventory_node_count"],
            "identity_count": model["identity_count"],
            "container_count": model["container_count"],
            "content_instance_count": model["content_instance_count"],
            "command_record_count": model["command_record_count"],
            "unmapped_telemetry_count": model["unmapped_telemetry_count"],
        },
        "kpi_evaluations": build_company_kpi_evaluations(model),
        "note": (
            "OneM2M resources are read from bounded company MongoDB testbed "
            "collections through the read proxy."
        ),
    }


def get_company_onem2m_command_flow_context(device_id=None):
    context = get_company_onem2m_device_resource_context(device_id)

    if context.get("source") != "company_mongodb":
        return context

    resources = context.get("resource_summary") or {}
    command_records = command_like_records(resources)

    context.update({
        "tool": "get_company_onem2m_command_flow",
        "command_record_count": (
            context.get("summary", {}).get("command_record_count", 0)
        ),
        "latest_command_cin_samples": command_records[:MAX_AGENT_SAMPLE_RECORDS],
        "flow_checks": {
            "identity_present": resources.get("IDENTITY", {}).get("present"),
            "ae_present": resources.get("AE", {}).get("present"),
            "command_container_present": (
                resources.get("CNT", {}).get("command_count", 0) > 0
            ),
            "subscription_present": resources.get("SUBSCRIPTION", {}).get("present"),
            "uri_mapper_present": resources.get("URI_MAPPER", {}).get("present"),
            "latest_command_cin_present": bool(command_records),
        },
        "next_diagnostic_step": (
            "Correlate latest command CIN with adapter/core logs and URI mapper "
            "target before blaming broker delivery."
        ),
    })
    return context


def get_company_onem2m_telemetry_flow_context(device_id=None):
    context = get_company_onem2m_device_resource_context(device_id)

    if context.get("source") != "company_mongodb":
        return context

    resources = context.get("resource_summary") or {}
    telemetry_records = telemetry_like_records(resources)

    context.update({
        "tool": "get_company_onem2m_telemetry_flow",
        "latest_telemetry_cin_samples": telemetry_records[:MAX_AGENT_SAMPLE_RECORDS],
        "kpi_evaluations": [
            evaluation
            for evaluation in context.get("kpi_evaluations", [])
            if evaluation.get("tool") == "get_company_onem2m_telemetry_flow"
        ],
        "flow_checks": {
            "identity_present": resources.get("IDENTITY", {}).get("present"),
            "ae_present": resources.get("AE", {}).get("present"),
            "telemetry_container_present": (
                resources.get("CNT", {}).get("telemetry_count", 0) > 0
            ),
            "backend_subscription_present": resources.get(
                "SUBSCRIPTION",
                {},
            ).get("present"),
            "latest_telemetry_cin_present": bool(telemetry_records),
        },
        "next_diagnostic_step": (
            "Compare adapter receive logs with CNT/CIN creation and subscription "
            "notification evidence."
        ),
    })
    return context


def scan_company_payload_threshold(threshold, limit=MAX_THRESHOLD_SCAN_RECORDS):
    safe_limit = max(1, min(int(limit), MAX_THRESHOLD_SCAN_RECORDS))
    database_name = os.getenv("COMPANY_OPERATIONAL_DB", "datamgmt")
    collection_name = os.getenv("COMPANY_OPERATIONAL_COLLECTION", "CIN")

    validate_identifier(database_name, "database name")
    validate_identifier(collection_name, "collection name")

    with get_company_mongo_read_proxy("company-llm-tools") as proxy:
        rows = proxy.find(
            database_name,
            collection_name,
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
            sort=DEFAULT_COMPANY_CIN_SORT,
            limit=safe_limit,
        )
        db_audit = proxy.get_audit_events()

    matches = []
    parseable_payloads = 0
    configured_metrics = sorted(configured_threshold_metric_names())

    for row in rows:
        parsed_payload = parse_payload_value(row.get("con"))

        if not isinstance(parsed_payload, (dict, list, int, float)):
            continue

        parseable_payloads += 1
        numeric_values = []
        collect_numeric_values(parsed_payload, "", numeric_values)

        for numeric_value_item in numeric_values:
            if not is_configured_threshold_metric(numeric_value_item["path"]):
                continue

            if numeric_value_item["value"] > threshold:
                matches.append({
                    "record_id": row.get("rn"),
                    "parent_container": row.get("pi"),
                    "timestamp": row.get("lt") or row.get("ct"),
                    "field": numeric_value_item["path"],
                    "value": numeric_value_item["value"],
                    "tenant_name": row.get("tenantName"),
                    "app_domain_name": row.get("appDomainName"),
                })

                if len(matches) >= MAX_THRESHOLD_MATCHES:
                    break

        if len(matches) >= MAX_THRESHOLD_MATCHES:
            break

    return {
        "source": "company_mongodb",
        "tool": "scan_company_threshold",
        "db_audit": db_audit,
        "rules_status": "configured_metric_scan",
        "rule_source": get_company_poc_rule_catalog(),
        "threshold": threshold,
        "configured_metric_fields": configured_metrics,
        "scanned_records": len(rows),
        "parseable_payloads": parseable_payloads,
        "match_count": len(matches),
        "matches": matches,
        "note": (
            "Threshold matching is limited to metric names present in the "
            "configured company rule catalog; metadata fields such as "
            "timestamp, locationId, operatorId, and inventorySessionId are "
            "excluded."
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
