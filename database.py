import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    try:
        cursor.execute("""
            ALTER TABLE chats ADD COLUMN user_id INTEGER
        """)
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            reasoning_steps TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
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

def get_device_telemetry_history(device_id, limit=30):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            timestamp,
            cpu_usage,
            memory_usage,
            heartbeat_delay,
            status
        FROM telemetry
        WHERE device_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (device_id, limit))

    rows = cursor.fetchall()

    conn.close()

    history = []

    for row in reversed(rows):
        history.append({
            "timestamp": row["timestamp"],
            "cpu_usage": row["cpu_usage"],
            "memory_usage": row["memory_usage"],
            "heartbeat_delay": row["heartbeat_delay"],
            "status": row["status"]
        })

    return history

def create_chat(user_id, title):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO chats (user_id, title, created_at)
        VALUES (?, ?, ?)
    """, (
        user_id,
        title,
        datetime.now().isoformat(timespec="seconds")
    ))

    chat_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return chat_id


def get_chats(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, created_at
        FROM chats
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "title": row[1],
            "created_at": row[2]
        }
        for row in rows
    ]


def add_message(chat_id, role, content, reasoning_steps=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO messages (
            chat_id,
            role,
            content,
            reasoning_steps,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        chat_id,
        role,
        content,
        reasoning_steps,
        datetime.now().isoformat(timespec="seconds")
    ))

    conn.commit()
    conn.close()


def get_messages(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role, content, reasoning_steps, created_at
        FROM messages
        WHERE chat_id = ?
        ORDER BY id ASC
    """, (chat_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "role": row[0],
            "content": row[1],
            "reasoning_steps": row[2],
            "created_at": row[3]
        }
        for row in rows
    ]

def create_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (username, password_hash, created_at)
        VALUES (?, ?, ?)
    """, (
        username,
        generate_password_hash(password),
        datetime.now().isoformat(timespec="seconds")
    ))

    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, username, password_hash
        FROM users
        WHERE username = ?
    """, (username,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "username": row[1],
        "password_hash": row[2]
    }


def verify_user(username, password):
    user = get_user_by_username(username)

    if not user:
        return None

    if not check_password_hash(user["password_hash"], password):
        return None

    return user

def delete_chat(chat_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM messages
        WHERE chat_id = ?
    """, (chat_id,))

    cursor.execute("""
        DELETE FROM chats
        WHERE id = ?
        AND user_id = ?
    """, (chat_id, user_id))

    conn.commit()
    conn.close()