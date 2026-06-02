import os

from database import (
    get_all_latest_devices as get_all_latest_devices_from_sqlite,
    get_device_telemetry_history as get_device_telemetry_history_from_sqlite,
    get_latest_status as get_latest_status_from_sqlite,
    insert_telemetry as insert_telemetry_into_sqlite,
)
from mongo_store import (
    get_all_latest_devices_from_mongo,
    get_device_telemetry_history_from_mongo,
    get_latest_status_from_mongo,
    insert_telemetry_if_enabled,
)


def get_telemetry_write_backend():
    return os.getenv("TELEMETRY_WRITE_BACKEND", "sqlite").lower()


def read_telemetry_from_mongo():
    return os.getenv("READ_TELEMETRY_FROM_MONGO", "false").lower() == "true"


def get_telemetry_source():
    return "mongodb" if read_telemetry_from_mongo() else "sqlite"


def write_telemetry(**telemetry):
    backend = get_telemetry_write_backend()

    if backend == "mongodb":
        return {
            "sqlite": False,
            "mongodb": insert_telemetry_if_enabled(**telemetry),
        }

    if backend == "dual":
        insert_telemetry_into_sqlite(**telemetry)
        return {
            "sqlite": True,
            "mongodb": insert_telemetry_if_enabled(**telemetry),
        }

    insert_telemetry_into_sqlite(**telemetry)
    return {
        "sqlite": True,
        "mongodb": False,
    }


def get_all_latest_devices():
    if read_telemetry_from_mongo():
        try:
            devices = get_all_latest_devices_from_mongo()
            if devices:
                return devices
        except Exception as exc:
            print(f"MongoDB telemetry read failed; falling back to SQLite: {exc}")

    return get_all_latest_devices_from_sqlite()


def get_latest_status(device_id):
    if read_telemetry_from_mongo():
        try:
            status = get_latest_status_from_mongo(device_id)
            if status:
                return status
        except Exception as exc:
            print(f"MongoDB telemetry read failed; falling back to SQLite: {exc}")

    return get_latest_status_from_sqlite(device_id)


def get_device_telemetry_history(device_id, limit=30):
    if read_telemetry_from_mongo():
        try:
            history = get_device_telemetry_history_from_mongo(device_id, limit)
            if history:
                return history
        except Exception as exc:
            print(f"MongoDB telemetry read failed; falling back to SQLite: {exc}")

    return get_device_telemetry_history_from_sqlite(device_id, limit)
