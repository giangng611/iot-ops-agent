def check_device_status():
    return {
        "device_id": "sensor-001",
        "status": "warning",
        "cpu_usage": "82%",
        "memory_usage": "71%",
        "last_heartbeat": "3 minutes ago"
    }


def get_recent_logs():
    return {
        "logs": [
            "sensor-001 heartbeat delayed",
            "temperature reading timeout",
            "MQTT reconnect attempt successful"
        ]
    }


def check_alarm_rules():
    return {
        "alarm": "High CPU usage",
        "severity": "medium",
        "threshold": "80%",
        "current_value": "82%"
    }


TOOLS = {
    "check_device_status": check_device_status,
    "get_recent_logs": get_recent_logs,
    "check_alarm_rules": check_alarm_rules
}