from database import get_latest_status, get_all_latest_devices


def check_device_status(device_id):
    latest = get_latest_status(device_id)

    if not latest:
        return {
            "error": "Device not found",
            "device_id": device_id
        }

    return {
        "device_id": latest["device_id"],
        "timestamp": latest["timestamp"],
        "status": latest["status"],
        "cpu_usage": f'{latest["cpu_usage"]}%',
        "memory_usage": f'{latest["memory_usage"]}%',
        "heartbeat_delay_seconds": latest["heartbeat_delay"]
    }


def get_recent_logs(device_id):
    latest = get_latest_status(device_id)

    if not latest:
        return {
            "error": "Device not found",
            "device_id": device_id
        }

    return {
        "device_id": latest["device_id"],
        "timestamp": latest["timestamp"],
        "logs": [
            latest["log_message"]
        ]
    }


def check_alarm_rules(device_id):
    latest = get_latest_status(device_id)

    if not latest:
        return {
            "error": "Device not found",
            "device_id": device_id
        }

    if not latest["alarm_name"]:
        return {
            "device_id": latest["device_id"],
            "timestamp": latest["timestamp"],
            "alarm": None,
            "severity": None
        }

    return {
        "device_id": latest["device_id"],
        "timestamp": latest["timestamp"],
        "alarm": latest["alarm_name"],
        "severity": latest["alarm_severity"]
    }


def get_all_devices():
    return get_all_latest_devices()



def check_system_overview(device_id=None):
    devices = get_all_latest_devices()

    unhealthy = [
        device for device in devices
        if device["status"] in ["warning", "critical"]
    ]

    return {
        "total_devices": len(devices),
        "healthy_count": len([
            device for device in devices
            if device["status"] == "healthy"
        ]),
        "warning_count": len([
            device for device in devices
            if device["status"] == "warning"
        ]),
        "critical_count": len([
            device for device in devices
            if device["status"] == "critical"
        ]),
        "unhealthy_devices": unhealthy
    }

def check_system_alarms(device_id=None):
    devices = get_all_latest_devices()

    alarms = []

    for device in devices:
        latest = get_latest_status(device["device_id"])

        if latest and latest["alarm_name"]:
            alarms.append({
                "device_id": latest["device_id"],
                "timestamp": latest["timestamp"],
                "alarm": latest["alarm_name"],
                "severity": latest["alarm_severity"],
                "status": latest["status"],
                "cpu_usage": latest["cpu_usage"],
                "memory_usage": latest["memory_usage"],
                "heartbeat_delay": latest["heartbeat_delay"]
            })

    return {
        "total_alarms": len(alarms),
        "active_alarms": alarms
    }

TOOLS = {
    "check_device_status": check_device_status,
    "get_recent_logs": get_recent_logs,
    "check_alarm_rules": check_alarm_rules,
    "check_system_overview": check_system_overview,
    "check_system_alarms": check_system_alarms
}