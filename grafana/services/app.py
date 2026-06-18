import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

from platform_service_health import get_platform_service_health
from services.grafana_client import (
    get_emqx_health,
    get_http_service_health,
    get_java_error_rate,
    get_k8s_health,
    get_linux_node_health,
    get_mongodb_health,
    get_mysql_health,
    get_otel_service_metrics,
    get_rabbitmq_queue_backlog,
    get_rabbitmq_throughput,
    get_redis_health,
    get_service_logs,
    get_service_trace_metrics,
)

app = Flask(__name__)


def _safe(fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        return jsonify(result)
    except KeyError as exc:
        return jsonify({"error": f"Missing env var: {exc}"}), 500
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.get("/health")
def health():
    return jsonify({"status": "ok", "grafana_base_url": os.environ.get("GRAFANA_BASE_URL")})


@app.get("/platform/service-health")
def platform_service_health():
    return _safe(get_platform_service_health)


@app.get("/grafana/queue-backlog")
def queue_backlog():
    return _safe(get_rabbitmq_queue_backlog)


@app.get("/grafana/throughput")
def throughput():
    queue = request.args.get("queue", ".+")
    return _safe(get_rabbitmq_throughput, queue=queue)


@app.get("/grafana/otel-metrics")
def otel_metrics():
    job = request.args.get("job", ".+")
    window = request.args.get("window", "5m")
    return _safe(get_otel_service_metrics, job=job, window=window)


@app.get("/grafana/http-health")
def http_health():
    project = request.args.get("project", ".+")
    job = request.args.get("job", ".+")
    window = request.args.get("window", "5m")
    return _safe(get_http_service_health, project=project, job=job, window=window)


@app.get("/grafana/java-errors")
def java_errors():
    window = request.args.get("window", "30m")
    return _safe(get_java_error_rate, window=window)


@app.get("/grafana/trace-metrics")
def trace_metrics():
    window = request.args.get("window", "30m")
    return _safe(get_service_trace_metrics, window=window)


@app.get("/grafana/logs")
def service_logs():
    return _safe(
        get_service_logs,
        service=request.args.get("service", ".+"),
        level=request.args.get("level", "error"),
        limit=int(request.args.get("limit", 20)),
        hours_back=int(request.args.get("hours_back", 1)),
    )


@app.get("/grafana/emqx")
def emqx_health():
    return _safe(get_emqx_health)


@app.get("/grafana/k8s")
def k8s_health():
    return _safe(get_k8s_health)


@app.get("/grafana/redis")
def redis_health():
    return _safe(get_redis_health)


@app.get("/grafana/mongodb")
def mongodb_health():
    return _safe(get_mongodb_health)


@app.get("/grafana/mysql")
def mysql_health():
    return _safe(get_mysql_health)


@app.get("/grafana/linux")
def linux_health():
    return _safe(get_linux_node_health)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
