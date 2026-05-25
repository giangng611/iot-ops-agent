import sqlite3
from datetime import datetime

DB_NAME = "telemetry.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            cpu_usage INTEGER NOT NULL,
            memory_usage INTEGER NOT NULL,
            heartbeat_delay INTEGER NOT NULL,
            status TEXT NOT NULL,
            log_message TEXT,
            alarm_name TEXT,
            alarm_severity TEXT
        )
    """)

    conn.commit()
    conn.close()


def insert_telemetry(device_id, cpu_usage, memory_usage, heartbeat_delay,
                     status, log_message=None, alarm_name=None, alarm_severity=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO telemetry (
            device_id,
            timestamp,
            cpu_usage,
            memory_usage,
            heartbeat_delay,
            status,
            log_message,
            alarm_name,
            alarm_severity
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        device_id,
        datetime.now().isoformat(timespec="seconds"),
        cpu_usage,
        memory_usage,
        heartbeat_delay,
        status,
        log_message,
        alarm_name,
        alarm_severity
    ))

    conn.commit()
    conn.close()


def get_latest_status(device_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT device_id, timestamp, cpu_usage, memory_usage,
               heartbeat_delay, status, log_message,
               alarm_name, alarm_severity
        FROM telemetry
        WHERE device_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (device_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "device_id": row[0],
        "timestamp": row[1],
        "cpu_usage": row[2],
        "memory_usage": row[3],
        "heartbeat_delay": row[4],
        "status": row[5],
        "log_message": row[6],
        "alarm_name": row[7],
        "alarm_severity": row[8]
    }


def get_all_latest_devices():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t1.device_id, t1.timestamp, t1.cpu_usage, t1.memory_usage,
               t1.heartbeat_delay, t1.status
        FROM telemetry t1
        INNER JOIN (
            SELECT device_id, MAX(timestamp) AS latest_timestamp
            FROM telemetry
            GROUP BY device_id
        ) t2
        ON t1.device_id = t2.device_id
        AND t1.timestamp = t2.latest_timestamp
        ORDER BY t1.device_id
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "device_id": row[0],
            "timestamp": row[1],
            "cpu_usage": row[2],
            "memory_usage": row[3],
            "heartbeat_delay": row[4],
            "status": row[5]
        }
        for row in rows
    ]