import json
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from database import DB_NAME, init_db  # noqa: E402
from mongo_store import get_telemetry_collection  # noqa: E402
from simulator import DEVICES, generate_telemetry  # noqa: E402
from telemetry_store import get_telemetry_write_backend  # noqa: E402


def sqlite_telemetry_count():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM telemetry")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def mongodb_telemetry_count():
    return get_telemetry_collection().count_documents({})


def main():
    init_db()

    before = {
        "sqlite": sqlite_telemetry_count(),
        "mongodb": mongodb_telemetry_count(),
    }

    for device_id in DEVICES:
        generate_telemetry(device_id)

    after = {
        "sqlite": sqlite_telemetry_count(),
        "mongodb": mongodb_telemetry_count(),
    }

    result = {
        "telemetry_write_backend": get_telemetry_write_backend(),
        "before": before,
        "after": after,
        "delta": {
            "sqlite": after["sqlite"] - before["sqlite"],
            "mongodb": after["mongodb"] - before["mongodb"],
        },
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
