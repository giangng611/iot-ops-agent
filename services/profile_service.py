from storage.relational_store import get_storage_status, get_user_usage_stats
from storage.telemetry_store import get_telemetry_source


def get_profile_usage_stats(user_id):
    stats = get_user_usage_stats(user_id)
    stats["storage"] = get_full_storage_status()
    return stats


def get_full_storage_status():
    return {
        **get_storage_status(),
        "telemetry": {
            "source": get_telemetry_source(),
        },
    }
