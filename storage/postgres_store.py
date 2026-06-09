import atexit
import os

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

try:
    from psycopg_pool import ConnectionPool
except ImportError:
    ConnectionPool = None

_pool = None
_pool_url = None


def get_postgres_connection_kwargs():
    statement_timeout_ms = int(
        os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "4000")
    )
    lock_timeout_ms = int(
        os.getenv("POSTGRES_LOCK_TIMEOUT_MS", "3000")
    )

    return {
        "row_factory": dict_row,
        "prepare_threshold": None,
        "connect_timeout": int(
            os.getenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", "5")
        ),
        "options": (
            f"-c statement_timeout={statement_timeout_ms} "
            f"-c lock_timeout={lock_timeout_ms}"
        ),
    }


def close_postgres_pool():
    global _pool
    global _pool_url

    if _pool is not None:
        _pool.close()
        _pool = None
        _pool_url = None


atexit.register(close_postgres_pool)


def get_postgres_url():
    return (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
    )


def postgres_url_configured():
    return bool(get_postgres_url())


def postgres_enabled():
    configured_backend = os.getenv("APP_DB_BACKEND")

    if configured_backend is None:
        return postgres_url_configured()

    return configured_backend.lower() in {
        "postgres",
        "supabase",
    }


def get_postgres_connection():
    if psycopg is None:
        raise RuntimeError(
            "psycopg is not installed. Run `pip install -r requirements.txt` "
            "before enabling Supabase/Postgres app data."
        )

    url = get_postgres_url()
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL, DATABASE_URL, or POSTGRES_URL is required."
        )

    if ConnectionPool is not None:
        global _pool
        global _pool_url

        if _pool is None or _pool_url != url:
            _pool = ConnectionPool(
                conninfo=url,
                kwargs=get_postgres_connection_kwargs(),
                min_size=int(os.getenv("POSTGRES_POOL_MIN_SIZE", "1")),
                max_size=int(os.getenv("POSTGRES_POOL_MAX_SIZE", "5")),
            )
            _pool_url = url

        return _pool.connection(
            timeout=float(os.getenv("POSTGRES_POOL_TIMEOUT_SECONDS", "5"))
        )

    return psycopg.connect(url, **get_postgres_connection_kwargs())


def apply_schema(schema_path):
    with open(schema_path, "r", encoding="utf-8") as file:
        schema_sql = file.read()

    with get_postgres_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(schema_sql)
        conn.commit()


def check_connection():
    with get_postgres_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("select current_database() as database, version() as version")
            return cursor.fetchone()


def reset_identity_sequence(conn, table_name):
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            select setval(
              pg_get_serial_sequence('public.{table_name}', 'id'),
              coalesce((select max(id) from public.{table_name}), 1),
              (select count(*) > 0 from public.{table_name})
            )
            """
        )
