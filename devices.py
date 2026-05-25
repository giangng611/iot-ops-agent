DEVICES = {
    "sensor-001": {
        "status": "warning",
        "cpu_usage": "82%",
        "memory_usage": "71%",
        "last_heartbeat": "3 minutes ago",
        "logs": [
            "heartbeat delayed",
            "temperature reading timeout",
            "MQTT reconnect attempt successful"
        ],
        "alarm": {
            "name": "High CPU usage",
            "severity": "medium",
            "threshold": "80%",
            "current_value": "82%"
        }
    },

    "sensor-002": {
        "status": "healthy",
        "cpu_usage": "42%",
        "memory_usage": "51%",
        "last_heartbeat": "20 seconds ago",
        "logs": [
            "normal telemetry transmission",
            "stable MQTT connection"
        ],
        "alarm": None
    },

    "gateway-003": {
        "status": "critical",
        "cpu_usage": "95%",
        "memory_usage": "89%",
        "last_heartbeat": "15 minutes ago",
        "logs": [
            "gateway timeout",
            "packet loss detected",
            "multiple reconnect failures"
        ],
        "alarm": {
            "name": "Gateway instability",
            "severity": "critical",
            "threshold": "90%",
            "current_value": "95%"
        }
    }
}