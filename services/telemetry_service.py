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
from services.company_data_service import get_company_operational_payload


def get_simulator_alerts(devices):
    critical_count = len([
        device for device in devices
        if device.get("status") == "critical"
    ])
    warning_count = len([
        device for device in devices
        if device.get("status") == "warning"
    ])

    return {
        "critical_count": critical_count,
        "warning_count": warning_count,
        "rules_status": "simulator",
    }


def get_devices_payload(selected_source="simulator"):
    if selected_source == "company":
        company_payload = get_company_operational_payload()

        if company_payload.get("source") != "simulator_fallback":
            return company_payload

        devices = company_payload["system_overview"].get("unhealthy_devices", [])
        all_devices = get_all_latest_devices()
        return {
            "source": "simulator_fallback",
            "selected_source": "company",
            "active_source": "simulator_fallback",
            "reason": company_payload.get("reason"),
            "rules_status": "simulator_fallback",
            "devices": all_devices or devices,
            "alerts": get_simulator_alerts(all_devices or devices),
        }

    devices = get_all_latest_devices()
    return {
        "source": get_telemetry_source(),
        "selected_source": "simulator",
        "active_source": get_telemetry_source(),
        "rules_status": "simulator",
        "devices": devices,
        "alerts": get_simulator_alerts(devices),
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
