import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.mongo_store import get_telemetry_health  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Check whether MongoDB is receiving simulator telemetry."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of latest telemetry documents to print.",
    )
    args = parser.parse_args()

    try:
        health = get_telemetry_health(limit=args.limit)
    except Exception as exc:
        print(f"MongoDB telemetry check failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(health, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
