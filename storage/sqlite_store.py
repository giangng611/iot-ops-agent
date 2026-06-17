import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from services.time_service import now_iso

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
            token_usage TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id)
        )
    """)

    try:
        cursor.execute("""
            ALTER TABLE messages ADD COLUMN token_usage TEXT
        """)
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            allowed_data_sources TEXT NOT NULL DEFAULT 'simulator',
            default_data_source TEXT NOT NULL DEFAULT 'simulator'
        )
    """)

    try:
        cursor.execute("""
            ALTER TABLE users ADD COLUMN allowed_data_sources TEXT
            NOT NULL DEFAULT 'simulator'
        """)
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("""
            ALTER TABLE users ADD COLUMN default_data_source TEXT
            NOT NULL DEFAULT 'simulator'
        """)
    except sqlite3.OperationalError:
        pass

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telegram_identities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            telegram_username TEXT,
            role TEXT NOT NULL DEFAULT 'viewer',
            allowed_data_sources TEXT NOT NULL DEFAULT 'simulator',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS telegram_identities_user_id_idx
        ON telegram_identities (user_id)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telegram_link_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_hash TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS telegram_link_codes_user_id_idx
        ON telegram_link_codes (user_id)
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
        now_iso(),
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


def get_all_telemetry_rows(limit=None, offset=0):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            id,
            device_id,
            timestamp,
            cpu_usage,
            memory_usage,
            heartbeat_delay,
            status,
            log_message,
            alarm_name,
            alarm_severity
        FROM telemetry
        ORDER BY id ASC
    """
    params = []

    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "device_id": row["device_id"],
            "timestamp": row["timestamp"],
            "cpu_usage": row["cpu_usage"],
            "memory_usage": row["memory_usage"],
            "heartbeat_delay": row["heartbeat_delay"],
            "status": row["status"],
            "log_message": row["log_message"],
            "alarm_name": row["alarm_name"],
            "alarm_severity": row["alarm_severity"],
        }
        for row in rows
    ]


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
            SELECT device_id, MAX(id) AS latest_id
            FROM telemetry
            GROUP BY device_id
        ) t2
        ON t1.device_id = t2.device_id
        AND t1.id = t2.latest_id
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
        now_iso()
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


def chat_belongs_to_user(chat_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 1
        FROM chats
        WHERE id = ?
        AND user_id = ?
        LIMIT 1
    """, (chat_id, user_id))

    row = cursor.fetchone()
    conn.close()

    return row is not None


def add_message(chat_id, role, content, reasoning_steps=None, token_usage=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO messages (
            chat_id,
            role,
            content,
            reasoning_steps,
            token_usage,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        role,
        content,
        reasoning_steps,
        token_usage,
        now_iso()
    ))

    conn.commit()
    conn.close()


def get_messages(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role, content, reasoning_steps, token_usage, created_at
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
            "token_usage": row[3],
            "created_at": row[4]
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
        now_iso()
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

def get_user_data_source_policy(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT allowed_data_sources, default_data_source
        FROM users
        WHERE id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "allowed_data_sources": ["simulator"],
            "default_data_source": "simulator",
        }

    allowed_sources = deserialize_data_sources(row[0])
    default_source = row[1] if row[1] in allowed_sources else "simulator"

    if "company" in allowed_sources:
        default_source = "company"

    return {
        "allowed_data_sources": allowed_sources or ["simulator"],
        "default_data_source": default_source,
    }

def update_user_data_source_policy(
    user_id,
    allowed_data_sources=None,
    default_data_source="simulator",
):
    allowed_sources = deserialize_data_sources(
        serialize_data_sources(allowed_data_sources)
    )

    if "simulator" not in allowed_sources:
        allowed_sources.insert(0, "simulator")

    if "company" in allowed_sources:
        default_data_source = "company"

    if default_data_source not in allowed_sources:
        default_data_source = "simulator"

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET allowed_data_sources = ?,
            default_data_source = ?
        WHERE id = ?
    """, (
        serialize_data_sources(allowed_sources),
        default_data_source,
        user_id,
    ))

    conn.commit()
    updated = cursor.rowcount
    conn.close()

    return updated > 0


def verify_user(username, password):
    user = get_user_by_username(username)

    if not user:
        return None

    if not check_password_hash(user["password_hash"], password):
        return None

    return user

def serialize_data_sources(data_sources):
    if isinstance(data_sources, str):
        data_sources = deserialize_data_sources(data_sources)

    return ",".join([
        str(item).strip()
        for item in (data_sources or ["simulator"])
        if str(item).strip()
    ]) or "simulator"

def deserialize_data_sources(value):
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]

def upsert_telegram_identity(
    telegram_user_id,
    user_id,
    telegram_username=None,
    role="viewer",
    allowed_data_sources=None,
    is_active=True,
):
    conn = get_connection()
    cursor = conn.cursor()
    timestamp = now_iso()

    cursor.execute("""
        INSERT INTO telegram_identities (
            telegram_user_id,
            user_id,
            telegram_username,
            role,
            allowed_data_sources,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            user_id = excluded.user_id,
            telegram_username = excluded.telegram_username,
            role = excluded.role,
            allowed_data_sources = excluded.allowed_data_sources,
            is_active = excluded.is_active,
            updated_at = excluded.updated_at
    """, (
        str(telegram_user_id),
        user_id,
        telegram_username,
        role or "viewer",
        serialize_data_sources(allowed_data_sources),
        1 if is_active else 0,
        timestamp,
        timestamp,
    ))

    conn.commit()
    conn.close()

def get_telegram_identity(telegram_user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            telegram_user_id,
            user_id,
            telegram_username,
            role,
            allowed_data_sources,
            is_active
        FROM telegram_identities
        WHERE telegram_user_id = ?
    """, (str(telegram_user_id),))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "telegram_user_id": row[0],
        "user_id": row[1],
        "telegram_username": row[2],
        "role": row[3],
        "allowed_data_sources": deserialize_data_sources(row[4]),
        "is_active": bool(row[5]),
    }

def create_telegram_link_code(code_hash, user_id, expires_at):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO telegram_link_codes (
            code_hash,
            user_id,
            expires_at,
            created_at
        )
        VALUES (?, ?, ?, ?)
    """, (
        code_hash,
        user_id,
        expires_at,
        now_iso(),
    ))

    conn.commit()
    conn.close()

def get_telegram_link_code(code_hash):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT code_hash, user_id, expires_at, used_at, created_at
        FROM telegram_link_codes
        WHERE code_hash = ?
    """, (code_hash,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "code_hash": row[0],
        "user_id": row[1],
        "expires_at": row[2],
        "used_at": row[3],
        "created_at": row[4],
    }

def mark_telegram_link_code_used(code_hash):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE telegram_link_codes
        SET used_at = ?
        WHERE code_hash = ?
        AND used_at IS NULL
    """, (now_iso(), code_hash))

    conn.commit()
    updated = cursor.rowcount
    conn.close()

    return updated > 0

def delete_chat(chat_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM messages
        WHERE chat_id IN (
            SELECT id
            FROM chats
            WHERE id = ?
            AND user_id = ?
        )
    """, (chat_id, user_id))

    cursor.execute("""
        DELETE FROM chats
        WHERE id = ?
        AND user_id = ?
    """, (chat_id, user_id))

    conn.commit()
    deleted = cursor.rowcount
    conn.close()

    return deleted > 0

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
