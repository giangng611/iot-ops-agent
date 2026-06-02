import os

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


def get_postgres_url():
    return (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
    )


def postgres_enabled():
    return os.getenv("APP_DB_BACKEND", "sqlite").lower() in {
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

    return psycopg.connect(url, row_factory=dict_row)


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
