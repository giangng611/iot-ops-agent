def get_platform_service_health():
    """
    Aggregates metrics from four Grafana dashboards via Prometheus.
    Maps to Bo_chi_so KPIs: API & Application (Diagnostic) + Ingestion (Core).
    Each sub-result is None when the Grafana call fails (network, auth, metric absent).
    overall_verdict = worst level across non-None sub-results; 'partial_data' if all None.
    """
    from services.grafana_client import (
        get_http_service_health,
        get_java_error_rate,
        get_rabbitmq_queue_backlog,
        get_rabbitmq_throughput,
    )

    def _try(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    http_health = _try(get_http_service_health)
    java_errors = _try(get_java_error_rate)
    queue_backlog = _try(get_rabbitmq_queue_backlog)
    throughput = _try(get_rabbitmq_throughput)

    level_order = {"critical": 0, "warning": 1, "good": 2}
    sub_levels = [
        r["level"]
        for r in [http_health, queue_backlog]
        if r is not None and "level" in r
    ]

    if not sub_levels:
        overall_verdict = "partial_data"
    else:
        overall_verdict = min(sub_levels, key=lambda l: level_order.get(l, 9))

    return {
        "source": "grafana_prometheus",
        "tool": "get_platform_service_health",
        "http_service_health": http_health,
        "java_error_rate": java_errors,
        "rabbitmq_queue_backlog": queue_backlog,
        "rabbitmq_throughput": throughput,
        "overall_verdict": overall_verdict,
        "kpi_mapping": {
            "api_latency_p95": "Bo_chi_so API & Application / Diagnostic",
            "http_error_rate": "Bo_chi_so API & Application / Diagnostic",
            "queue_backlog": "Bo_chi_so Ingestion / Core",
            "telemetry_throughput": "Bo_chi_so Ingestion / Core",
        },
        "disclaimer": (
            "Instantaneous Prometheus snapshots. Template variables ($project, $job) "
            "use .+ regex (all services). Loki/Tempo panels from the Java error "
            "dashboard are excluded (different datasource)."
        ),
    }
