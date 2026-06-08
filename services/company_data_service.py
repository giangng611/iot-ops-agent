import os
import re

import psycopg
from psycopg.rows import dict_row

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


def get_company_db_url():
    return (
        os.getenv("COMPANY_DB_URL")
        or os.getenv("COMPANY_POSTGRES_URL")
        or os.getenv("IOT_PLATFORM_DB_URL")
    )


def company_db_configured():
    return bool(get_company_db_url())


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
        tables = list_company_tables(table_limit)
    except Exception as exc:
        return simulator_fallback_snapshot(
            f"Company DB probe failed: {exc}"
        )

    return {
        "source": "company_postgres",
        "tables": tables,
    }
