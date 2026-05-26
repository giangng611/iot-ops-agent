import random
import time

from database import init_db, insert_telemetry

DEVICES = [
    "sensor-001",
    "sensor-002",
    "sensor-003",
    "sensor-004",
    "sensor-005",
    "sensor-006",
    "sensor-007",
    "gateway-001",
    "gateway-002",
    "gateway-003"
]

SIMULATION_INTERVAL_SECONDS = 30


def determine_status(cpu, memory, heartbeat_delay):
    if cpu >= 90 or memory >= 90 or heartbeat_delay >= 600:
        return "critical"

    if cpu >= 75 or memory >= 80 or heartbeat_delay >= 180:
        return "warning"

    return "healthy"


def generate_log(status):
    if status == "critical":
        return random.choice([
            "gateway timeout",
            "packet loss detected",
            "multiple reconnect failures",
            "device heartbeat missing",
            "high resource usage detected"
        ])

    if status == "warning":
        return random.choice([
            "heartbeat delayed",
            "temperature reading timeout",
            "MQTT reconnect attempt successful",
            "temporary latency spike detected"
        ])

    return random.choice([
        "normal telemetry transmission",
        "stable MQTT connection",
        "device operating normally",
        "heartbeat received successfully"
    ])


def generate_alarm(status, cpu, memory, heartbeat_delay):
    if status == "critical":
        if heartbeat_delay >= 600:
            return "Heartbeat delay exceeded", "critical"

        if cpu >= 90:
            return "Critical CPU usage", "critical"

        if memory >= 90:
            return "Critical memory usage", "critical"

    if status == "warning":
        if heartbeat_delay >= 180:
            return "Heartbeat delay warning", "medium"

        if cpu >= 75:
            return "High CPU usage", "medium"

        if memory >= 80:
            return "High memory usage", "medium"

    return None, None

def generate_telemetry(device_id):
    if device_id.startswith("gateway"):
        cpu = random.randint(45, 96)
        memory = random.randint(45, 94)
        heartbeat_delay = random.randint(10, 750)

    elif device_id in ["sensor-001", "sensor-004", "sensor-007"]:
        cpu = random.randint(45, 88)
        memory = random.randint(40, 86)
        heartbeat_delay = random.randint(10, 360)

    else:
        cpu = random.randint(25, 70)
        memory = random.randint(30, 72)
        heartbeat_delay = random.randint(5, 120)

    status = determine_status(cpu, memory, heartbeat_delay)
    log_message = generate_log(status)
    alarm_name, alarm_severity = generate_alarm(
        status,
        cpu,
        memory,
        heartbeat_delay
    )

    insert_telemetry(
        device_id=device_id,
        cpu_usage=cpu,
        memory_usage=memory,
        heartbeat_delay=heartbeat_delay,
        status=status,
        log_message=log_message,
        alarm_name=alarm_name,
        alarm_severity=alarm_severity
    )


def main():
    init_db()

    while True:
        for device_id in DEVICES:
            generate_telemetry(device_id)

        print(f"Inserted telemetry batch for {len(DEVICES)} devices.")
        time.sleep(SIMULATION_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()