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

    try:
        cursor.execute("""
            ALTER TABLE chats ADD COLUMN is_pinned INTEGER DEFAULT 0
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

    CREATE_PROMPTS_TABLE = """
    CREATE TABLE IF NOT EXISTS prompts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        command TEXT NOT NULL,
        category TEXT NOT NULL,
        is_default INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    cursor.execute(CREATE_PROMPTS_TABLE)

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
        SELECT id, title, created_at, is_pinned
        FROM chats
        WHERE user_id = ?
        ORDER BY is_pinned DESC, id DESC
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "title": row[1],
            "created_at": row[2],
            "is_pinned": bool(row[3])
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

def toggle_pin_chat(chat_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT is_pinned
        FROM chats
        WHERE id = ?
        AND user_id = ?
    """, (chat_id, user_id))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    new_value = 0 if row[0] else 1

    cursor.execute("""
        UPDATE chats
        SET is_pinned = ?
        WHERE id = ?
        AND user_id = ?
    """, (new_value, chat_id, user_id))

    conn.commit()
    conn.close()

    return bool(new_value)

def change_user_password(user_id, current_password, new_password):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT password_hash
        FROM users
        WHERE id = ?
    """, (user_id,))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return False, "User not found"

    if not check_password_hash(row[0], current_password):
        conn.close()
        return False, "Current password is incorrect"

    cursor.execute("""
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
    """, (
        generate_password_hash(new_password),
        user_id
    ))

    conn.commit()
    conn.close()

    return True, "Password updated successfully"

def get_prompts(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, command, category, is_default
        FROM prompts
        WHERE user_id = ? OR is_default = 1
        ORDER BY is_default DESC, id DESC
    """, (user_id,))

    rows = cursor.fetchall()

    prompts = []
    for row in rows:
        prompts.append({
            "id": row[0],
            "title": row[1],
            "command": row[2],
            "category": row[3],
            "is_default": row[4]
        })

    conn.close()
    return prompts

def create_prompt(user_id, title, command, category):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO prompts (user_id, title, command, category, is_default)
        VALUES (?, ?, ?, ?, 0)
    """, (user_id, title, command, category))

    conn.commit()
    prompt_id = cursor.lastrowid
    conn.close()

    return prompt_id

def update_prompt(prompt_id, user_id, title, command, category):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE prompts
        SET title = ?, command = ?, category = ?
        WHERE id = ? AND user_id = ? AND is_default = 0
    """, (title, command, category, prompt_id, user_id))

    conn.commit()
    updated = cursor.rowcount
    conn.close()

    return updated > 0

def delete_prompt(prompt_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM prompts
        WHERE id = ? AND user_id = ? AND is_default = 0
    """, (prompt_id, user_id))

    conn.commit()
    deleted = cursor.rowcount
    conn.close()

    return deleted > 0

def update_username(user_id, new_username):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET username = ?
        WHERE id = ?
    """, (new_username, user_id))

    conn.commit()
    updated = cursor.rowcount
    conn.close()

    return updated > 0

def delete_user_account(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM messages
        WHERE chat_id IN (
            SELECT id FROM chats WHERE user_id = ?
        )
    """, (user_id,))

    cursor.execute("""
        DELETE FROM chats
        WHERE user_id = ?
    """, (user_id,))

    cursor.execute("""
        DELETE FROM prompts
        WHERE user_id = ?
        AND is_default = 0
    """, (user_id,))

    cursor.execute("""
        DELETE FROM users
        WHERE id = ?
    """, (user_id,))

    conn.commit()
    deleted = cursor.rowcount
    conn.close()

    return deleted > 0

def get_user_usage_stats(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM chats
        WHERE user_id = ?
    """, (user_id,))
    chat_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM messages
        WHERE chat_id IN (
            SELECT id FROM chats WHERE user_id = ?
        )
    """, (user_id,))
    message_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM prompts
        WHERE user_id = ?
        AND is_default = 0
    """, (user_id,))
    custom_prompt_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT device_id)
        FROM telemetry
    """)
    device_count = cursor.fetchone()[0]

    conn.close()

    return {
        "chat_count": chat_count,
        "message_count": message_count,
        "custom_prompt_count": custom_prompt_count,
        "device_count": device_count
    }