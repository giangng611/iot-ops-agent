from storage.mongo_store import (
    ensure_telemetry_indexes,
    get_all_latest_devices_from_mongo,
    get_device_telemetry_history_from_mongo,
    get_telemetry_health,
    get_telemetry_indexes,
)
from storage.telemetry_store import (
    get_all_latest_devices,
    get_device_telemetry_history,
    get_telemetry_source,
)


def get_devices_payload():
    return {
        "source": get_telemetry_source(),
        "devices": get_all_latest_devices(),
    }


def get_device_history_payload(device_id):
    return {
        "source": get_telemetry_source(),
        "device_id": device_id,
        "history": get_device_telemetry_history(device_id),
    }


def get_mongo_telemetry_health_payload(limit):
    return get_telemetry_health(limit=limit)


def get_mongo_telemetry_indexes_payload(ensure_indexes=False):
    if ensure_indexes:
        ensure_telemetry_indexes()

    return get_telemetry_indexes()


def get_mongo_devices_payload():
    return {
        "source": "mongodb",
        "devices": get_all_latest_devices_from_mongo(),
    }


def get_mongo_device_history_payload(device_id, limit):
    return {
        "source": "mongodb",
        "device_id": device_id,
        "history": get_device_telemetry_history_from_mongo(device_id, limit=limit),
    }
