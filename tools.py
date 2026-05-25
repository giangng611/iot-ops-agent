from devices import DEVICES

def check_device_status(device_id):
    device = DEVICES.get(device_id)

    if not device:
        return {"error": "Device not found"}

    return {
        "device_id": device_id,
        "status": device["status"],
        "cpu_usage": device["cpu_usage"],
        "memory_usage": device["memory_usage"],
        "last_heartbeat": device["last_heartbeat"]
    }


def get_recent_logs(device_id):
    device = DEVICES.get(device_id)

    if not device:
        return {"error": "Device not found"}

    return {
        "device_id": device_id,
        "logs": device["logs"],
    }


def check_alarm_rules(device_id):
    device = DEVICES.get(device_id)

    if not device:
        return {"error": "Device not found"}

    alarm = device.get("alarm")
    if not alarm:
        return {
            "device_id": device_id,
            "alarm": None
        }

    return {
        "device_id": device_id,
        "alarm": alarm["name"],
        "severity": alarm["severity"],
        "threshold": alarm["threshold"],
        "current_value": alarm["current_value"]
    }

def get_all_devices():
    return [
        {"device_id": device_id, "status": data["status"]}
        for device_id, data in DEVICES.items()
    ]

TOOLS = {
    "check_device_status": check_device_status,
    "get_recent_logs": get_recent_logs,
    "check_alarm_rules": check_alarm_rules
}