import argparse

from flask import Flask, jsonify, request


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "mock_grafana_dashboard_client"})


@app.get("/platform/service-health")
def platform_service_health():
    return jsonify({
        "overall_verdict": "warning",
        "dashboards": {
            "rabbitmq": "good",
            "http": "warning",
            "k8s": "good",
            "redis": "warning",
        },
    })


@app.get("/grafana/queue-backlog")
def queue_backlog():
    return jsonify({
        "level": "good",
        "total_messages": 42,
        "queues": [
            {"queue": "queue.onem2m.orchestration", "messages": 17},
            {"queue": "queue.telemetry.ingest", "messages": 25},
        ],
    })


@app.get("/grafana/throughput")
def throughput():
    queue = request.args.get("queue")
    return jsonify({
        "level": "good",
        "queue": queue or "all",
        "publish_rate": 128.4,
        "ack_rate": 126.9,
        "lag_rate": 1.5,
    })


@app.get("/grafana/http-health")
def http_health():
    return jsonify({
        "level": "warning",
        "project": request.args.get("project", "all"),
        "window": request.args.get("window", "5m"),
        "request_rate": 322.5,
        "error_rate_percent": 1.7,
        "latency_p95_ms": 420,
    })


@app.get("/grafana/java-errors")
def java_errors():
    return jsonify({
        "level": "good",
        "window": request.args.get("window", "5m"),
        "error_rate_percent": 0.2,
    })


@app.get("/grafana/trace-metrics")
def trace_metrics():
    return jsonify({
        "level": "warning",
        "window": request.args.get("window", "5m"),
        "services": [
            {"service": "iot-core-accounting-api", "error_rate_percent": 0.8, "latency_p95_ms": 360},
            {"service": "iot-core-device-api", "error_rate_percent": 1.1, "latency_p95_ms": 510},
        ],
    })


@app.get("/grafana/logs")
def logs():
    return jsonify({
        "level": request.args.get("level", "error"),
        "service": request.args.get("service", "all"),
        "hours_back": request.args.get("hours_back", "1"),
        "logs": [
            {
                "timestamp": "2026-06-18T04:40:00Z",
                "service": request.args.get("service", "emqx"),
                "message": "Mock error log for local n8n workflow validation.",
            }
        ],
    })


@app.get("/grafana/emqx")
def emqx():
    return jsonify({
        "level": "good",
        "connections": 1240,
        "message_rate": 950.3,
        "drop_rate": 0.01,
    })


@app.get("/grafana/k8s")
def k8s():
    return jsonify({
        "level": "good",
        "cluster_cpu_percent": 48.5,
        "pod_restarts": 2,
        "pod_phases": {"Running": 128, "Pending": 1, "Failed": 0},
    })


@app.get("/grafana/redis")
def redis():
    return jsonify({
        "level": "warning",
        "connected_clients": 84,
        "ops_rate": 2200,
        "hit_rate_percent": 47.2,
        "memory_used_percent": 63.5,
    })


@app.get("/grafana/mongodb")
def mongodb():
    return jsonify({
        "level": "good",
        "instances_up": 3,
        "avg_latency_ms": 12.4,
        "ops_rate_per_sec": None,
    })


@app.get("/grafana/mysql")
def mysql():
    return jsonify({
        "level": "good",
        "instances_up": 2,
        "qps": 512.8,
        "threads_connected": 34,
        "slow_query_count": 0,
    })


@app.get("/grafana/linux")
def linux():
    return jsonify({
        "level": "warning",
        "cpu_percent": 71.2,
        "memory_percent": 68.1,
        "disk_percent": 82.4,
        "network_rx_rate": 1048576,
    })


def main():
    parser = argparse.ArgumentParser(
        description="Run a local mock Grafana Dashboard Client for IOA v3 n8n testing.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()

    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
