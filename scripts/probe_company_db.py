import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from services.company_data_service import (  # noqa: E402
    company_db_type,
    inspect_company_mongo_collection_schema,
    preview_company_mongo_collection,
    preview_company_table,
    probe_company_db,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Probe the company operational DB with read-only, low-limit queries. "
            "Falls back to simulator telemetry when COMPANY_DB_URL is unavailable."
        )
    )
    parser.add_argument(
        "--table-limit",
        type=int,
        default=20,
        help="Maximum number of tables/views to list.",
    )
    parser.add_argument(
        "--preview",
        help=(
            "Optional preview target. Use schema.table for Postgres or "
            "database.collection for MongoDB."
        ),
    )
    parser.add_argument(
        "--inspect",
        help=(
            "Inspect field paths and types without printing values. "
            "MongoDB only, in database.collection format."
        ),
    )
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=5,
        help="Maximum rows to preview from the selected table.",
    )
    args = parser.parse_args()

    if args.inspect:
        if "." not in args.inspect:
            raise RuntimeError("--inspect must use database.collection format.")

        database_name, collection_name = args.inspect.split(".", 1)
        payload = inspect_company_mongo_collection_schema(
            database_name,
            collection_name,
            args.preview_limit,
        )
    elif args.preview:
        if "." not in args.preview:
            raise RuntimeError(
                "--preview must use schema.table or database.collection format."
            )

        namespace, object_name = args.preview.split(".", 1)

        if company_db_type() == "mongodb":
            payload = preview_company_mongo_collection(
                namespace,
                object_name,
                args.preview_limit,
            )
        else:
            payload = preview_company_table(
                namespace,
                object_name,
                args.preview_limit,
            )
    else:
        payload = probe_company_db(args.table_limit)

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
