import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from mongo_store import ensure_telemetry_indexes, get_telemetry_indexes  # noqa: E402


def main():
    try:
        result = ensure_telemetry_indexes()
        indexes = get_telemetry_indexes()
    except Exception as exc:
        print(f"MongoDB index setup failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Created/verified indexes:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\nCurrent index definitions:")
    print(json.dumps(indexes, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
