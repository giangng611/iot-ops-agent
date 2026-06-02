import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.sqlite_store import get_all_telemetry_rows  # noqa: E402
from storage.mongo_store import ensure_telemetry_indexes, upsert_sqlite_telemetry_row  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Backfill SQLite telemetry rows into MongoDB."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of SQLite telemetry rows to process per batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows without writing to MongoDB.",
    )
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")

    offset = 0
    processed = 0
    inserted = 0
    already_present = 0

    if not args.dry_run:
        ensure_telemetry_indexes()

    while True:
        rows = get_all_telemetry_rows(limit=args.batch_size, offset=offset)

        if not rows:
            break

        if args.dry_run:
            processed += len(rows)
            offset += args.batch_size
            continue

        for row in rows:
            result = upsert_sqlite_telemetry_row(row)
            processed += 1

            if result["upserted"]:
                inserted += 1
            else:
                already_present += 1

        print(
            "Processed "
            f"{processed} rows | inserted={inserted} | "
            f"already_present={already_present}"
        )
        offset += args.batch_size

    if args.dry_run:
        print(f"Dry run complete. SQLite telemetry rows found: {processed}")
        return

    print(
        "Backfill complete. "
        f"processed={processed}, inserted={inserted}, "
        f"already_present={already_present}"
    )


if __name__ == "__main__":
    main()
