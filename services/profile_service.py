from storage.relational_store import (
    get_storage_status,
    get_user_data_source_policy,
    get_user_usage_stats,
)
from storage.telemetry_store import get_telemetry_source
from services.company_data_service import get_company_operational_payload


def get_profile_usage_stats(user_id, selected_source=None):
    stats = get_user_usage_stats(user_id)
    stats.update(get_device_monitoring_stats(user_id, selected_source))
    stats["storage"] = get_full_storage_status()
    return stats


def get_device_monitoring_stats(user_id, selected_source=None):
    selected_source = selected_source or get_user_data_source_policy(user_id).get(
        "default_data_source",
        "simulator",
    )

    if selected_source == "company":
        try:
            payload = get_company_operational_payload()
        except Exception as exc:
            return {
                "device_count_source": "company_mongodb_unavailable",
                "device_count_error": type(exc).__name__,
            }

        if payload.get("source") == "company_mongodb":
            devices = payload.get("devices") or []
            return {
                "device_count": len(devices),
                "device_count_source": "company_mongodb",
            }

        return {
            "device_count_source": payload.get("source") or "simulator_fallback",
            "device_count_reason": payload.get("reason"),
        }

    return {
        "device_count": stats_device_count_from_telemetry(),
        "device_count_source": get_telemetry_source(),
    }


def stats_device_count_from_telemetry():
    try:
        from storage.telemetry_store import get_all_latest_devices

        return len(get_all_latest_devices())
    except Exception:
        return 0


def get_full_storage_status():
    return {
        **get_storage_status(),
        "telemetry": {
            "source": get_telemetry_source(),
        },
    }
