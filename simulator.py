import random
import time

from database import init_db, insert_telemetry

DEVICES = ["sensor-001", "sensor-002", "gateway-003"]


def determine_status(cpu, memory, heartbeat_delay):
    if cpu >= 90 or memory >= 90 or heartbeat_delay >= 600:
        return "critical"

    if cpu >= 75 or memory >= 75 or heartbeat_delay >= 180:
        return "warning"

    return "healthy"


def generate_log(status):
    if status == "critical":
        return random.choice([
            "gateway timeout",
            "packet loss detected",
            "multiple reconnect failures",
            "device heartbeat missing"
        ])

    if status == "warning":
        return random.choice([
            "heartbeat delayed",
            "temperature reading timeout",
            "MQTT reconnect attempt successful"
        ])

    return random.choice([
        "normal telemetry transmission",
        "stable MQTT connection",
        "device operating normally"
    ])


def generate_alarm(status, cpu):
    if status == "critical":
        return "Critical resource usage", "critical"

    if status == "warning" and cpu >= 75:
        return "High CPU usage", "medium"

    return None, None


def generate_telemetry(device_id):
    if device_id == "sensor-002":
        cpu = random.randint(30, 55)
        memory = random.randint(40, 60)
        heartbeat_delay = random.randint(5, 30)

    elif device_id == "sensor-001":
        cpu = random.randint(65, 85)
        memory = random.randint(60, 78)
        heartbeat_delay = random.randint(60, 240)

    else:
        cpu = random.randint(80, 98)
        memory = random.randint(75, 95)
        heartbeat_delay = random.randint(180, 900)

    status = determine_status(cpu, memory, heartbeat_delay)
    log_message = generate_log(status)
    alarm_name, alarm_severity = generate_alarm(status, cpu)

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

        print("Inserted new telemetry batch.")
        time.sleep(60)


if __name__ == "__main__":
    main()