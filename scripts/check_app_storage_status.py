import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from storage.relational_store import get_storage_status  # noqa: E402
from storage.telemetry_store import get_telemetry_source  # noqa: E402


def main():
    status = get_storage_status()
    status["telemetry"] = {
        "source": get_telemetry_source(),
    }

    print(json.dumps(status, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
