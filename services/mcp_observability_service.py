import os
import time
from datetime import datetime, timezone

from services.mcp_client import call_mcp_tool


DEFAULT_LOKI_NAMESPACE = "one-iot"
DEFAULT_RABBITMQ_NAMESPACE = "test"
DEFAULT_K8S_NAMESPACE = "one-iot"
_DATASOURCE_UID_CACHE = {}


def _is_transient_mcp_error(exc):
    message = str(exc).lower()
    return (
        "429" in message
        or "too many requests" in message
        or "taskgroup" in message
        or "temporarily" in message
    )


def _call_mcp_tool_with_retries(tool_name, payload, *, attempts=3):
    last_error = None
    for attempt in range(attempts):
        try:
            return call_mcp_tool(tool_name, payload)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts - 1 or not _is_transient_mcp_error(exc):
                raise
            time.sleep(0.75 * (attempt + 1))

    raise last_error


def _coerce_positive_int(value, default, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(1, min(parsed, maximum))


def _find_datasource_uid(datasource_type):
    datasource_type = str(datasource_type or "").lower()
    if datasource_type in _DATASOURCE_UID_CACHE:
        return _DATASOURCE_UID_CACHE[datasource_type]

    datasources = _call_mcp_tool_with_retries("grafana_list_datasources", {})

    if isinstance(datasources, dict) and datasources.get("level") == "unavailable":
        message = datasources.get("message") or datasources.get("error") or "unknown Grafana datasource discovery error"
        raise RuntimeError(
            f"Grafana datasource discovery failed: {datasources.get('error_type') or 'Error'}: {message}"
        )

    for datasource in datasources or []:
        if not isinstance(datasource, dict):
            continue

        if str(datasource.get("type") or "").lower() == datasource_type:
            _DATASOURCE_UID_CACHE[datasource_type] = datasource.get("uid")
            return _DATASOURCE_UID_CACHE[datasource_type]

    return None


def _unix_seconds(value):
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()

    if text.isdigit():
        return int(text)

    try:
        normalized = text.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return None


def _bounded_range(start=None, end=None, step=None, default_hours=1):
    safe_end = _unix_seconds(end) or int(time.time())
    safe_start = _unix_seconds(start) or safe_end - default_hours * 3600

    if safe_start >= safe_end:
        safe_start = safe_end - default_hours * 3600

    safe_step = _coerce_positive_int(step, 300, 3600)
    return safe_start, safe_end, safe_step


def _query_prometheus_instant(promql_query):
    try:
        datasource_uid = _find_datasource_uid("prometheus")
    except Exception as exc:
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_list_datasources",
            "level": "unavailable",
            "error": str(exc),
            "promql_query": promql_query,
        }

    if not datasource_uid:
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "level": "unavailable",
            "error": "No Prometheus datasource was found through MCP Grafana datasource discovery.",
            "promql_query": promql_query,
        }

    try:
        result = _call_mcp_tool_with_retries(
            "grafana_query",
            {
                "datasource_uid": datasource_uid,
                "promql_query": promql_query,
            },
        )
    except Exception as exc:
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "level": "unavailable",
            "error": str(exc),
            "promql_query": promql_query,
        }

    return {
        "source": "mcp_server",
        "mcp_tool": "grafana_query",
        "promql_query": promql_query,
        "result": result,
    }


def _query_prometheus_instant_map(queries, *, pause_seconds=0.2):
    results = {}
    for index, (name, query) in enumerate(queries.items()):
        if index:
            time.sleep(pause_seconds)
        results[name] = _query_prometheus_instant(query)
    return results


def _query_prometheus_range(promql_query, *, start=None, end=None, step=None):
    safe_start, safe_end, safe_step = _bounded_range(start, end, step)
    try:
        datasource_uid = _find_datasource_uid("prometheus")
    except Exception as exc:
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_list_datasources",
            "level": "unavailable",
            "error": str(exc),
            "promql_query": promql_query,
            "start": safe_start,
            "end": safe_end,
            "step": safe_step,
        }

    if not datasource_uid:
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query_range",
            "level": "unavailable",
            "error": "No Prometheus datasource was found through MCP Grafana datasource discovery.",
            "promql_query": promql_query,
            "start": safe_start,
            "end": safe_end,
            "step": safe_step,
        }

    try:
        result = _call_mcp_tool_with_retries(
            "grafana_query_range",
            {
                "datasource_uid": datasource_uid,
                "promql_query": promql_query,
                "start": safe_start,
                "end": safe_end,
                "step": safe_step,
            },
        )
    except Exception as exc:
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query_range",
            "level": "unavailable",
            "error": str(exc),
            "promql_query": promql_query,
            "start": safe_start,
            "end": safe_end,
            "step": safe_step,
        }

    return {
        "source": "mcp_server",
        "mcp_tool": "grafana_query_range",
        "promql_query": promql_query,
        "start": safe_start,
        "end": safe_end,
        "step": safe_step,
        "result": result,
    }


def query_iot_platform_metric_via_mcp(tool_name, params=None):
    params = params or {}

    if tool_name == "grafana_queue_backlog":
        namespace = params.get("namespace") or DEFAULT_RABBITMQ_NAMESPACE
        topk = _coerce_positive_int(params.get("topk"), 10, 50)
        threshold = _coerce_positive_int(params.get("threshold"), 10000, 1000000000)
        promql = (
            f'topk({topk}, sum by (queue) '
            f'(rabbitmq_queue_messages{{namespace="{namespace}",job="monitoring/rabbitmq"}}))'
        )
        evidence = _query_prometheus_instant(promql)
        evidence.update({
            "scenario": "8",
            "tool": tool_name,
            "request": {
                "namespace": namespace,
                "topk": topk,
                "threshold": threshold,
            },
            "expected_metric": "rabbitmq_queue_messages",
        })
        return evidence

    if tool_name == "grafana_queue_trend":
        namespace = params.get("namespace") or DEFAULT_RABBITMQ_NAMESPACE
        promql = (
            f'sum by (queue) '
            f'(rabbitmq_queue_messages{{namespace="{namespace}",job="monitoring/rabbitmq"}})'
        )
        evidence = _query_prometheus_range(
            promql,
            start=params.get("start"),
            end=params.get("end"),
            step=params.get("step"),
        )
        evidence.update({
            "scenario": "9",
            "tool": tool_name,
            "request": {
                "namespace": namespace,
                "queue": params.get("queue"),
                "start": evidence.get("start"),
                "end": evidence.get("end"),
                "step": evidence.get("step"),
            },
            "expected_metric": "rabbitmq_queue_messages",
        })
        return evidence

    if tool_name == "query_rabbitmq_queue_detail":
        namespace = params.get("namespace") or DEFAULT_RABBITMQ_NAMESPACE
        queue_name = str(params.get("queue_name") or params.get("queue") or "").strip()
        queue_filter = f',queue="{queue_name}"' if queue_name else ""
        queries = _query_prometheus_instant_map({
            "messages": (
                f'sum(rabbitmq_queue_messages{{namespace="{namespace}",'
                f'job="monitoring/rabbitmq"{queue_filter}}})'
            ),
            "messages_ready": (
                f'sum(rabbitmq_queue_messages_ready{{namespace="{namespace}",'
                f'job="monitoring/rabbitmq"{queue_filter}}})'
            ),
            "messages_unacked": (
                f'sum(rabbitmq_queue_messages_unacked{{namespace="{namespace}",'
                f'job="monitoring/rabbitmq"{queue_filter}}})'
            ),
            "consumers": (
                f'sum(rabbitmq_queue_consumers{{namespace="{namespace}",'
                f'job="monitoring/rabbitmq"{queue_filter}}})'
            ),
            "deliver_rate": (
                f'sum(rate(rabbitmq_queue_messages_delivered_total{{namespace="{namespace}",'
                f'job="monitoring/rabbitmq"{queue_filter}}}[5m]))'
            ),
            "publish_rate": (
                f'sum(rate(rabbitmq_queue_messages_published_total{{namespace="{namespace}",'
                f'job="monitoring/rabbitmq"{queue_filter}}}[5m]))'
            ),
        })
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "scenario": "8_drilldown",
            "tool": tool_name,
            "request": {
                "namespace": namespace,
                "queue_name": queue_name or None,
            },
            "expected_metrics": list(queries.keys()),
            "queries": queries,
        }

    if tool_name == "grafana_emqx_dropped_trend":
        promql = 'sum(emqx_messages_dropped{namespace="emqx",job="emqx"})'
        evidence = _query_prometheus_range(
            promql,
            start=params.get("start"),
            end=params.get("end"),
            step=params.get("step"),
        )
        evidence.update({
            "scenario": "10",
            "tool": tool_name,
            "request": {
                "start": evidence.get("start"),
                "end": evidence.get("end"),
                "step": evidence.get("step"),
            },
            "expected_metric": "emqx_messages_dropped",
        })
        return evidence

    if tool_name == "grafana_emqx_connection_trend":
        connected_query = (
            'sum(rate(emqx_client_connected{namespace="emqx",job="emqx"}[1m]))'
        )
        disconnected_query = (
            'sum(rate(emqx_client_disconnected{namespace="emqx",job="emqx"}[1m]))'
        )
        connected = _query_prometheus_range(
            connected_query,
            start=params.get("start"),
            end=params.get("end"),
            step=params.get("step"),
        )
        disconnected = _query_prometheus_range(
            disconnected_query,
            start=params.get("start"),
            end=params.get("end"),
            step=params.get("step"),
        )
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query_range",
            "scenario": "11",
            "tool": tool_name,
            "request": {
                "device_scope": "all",
                "start": connected.get("start"),
                "end": connected.get("end"),
                "step": connected.get("step"),
            },
            "expected_metrics": [
                "emqx_client_connected",
                "emqx_client_disconnected",
            ],
            "queries": {
                "connected": connected,
                "disconnected": disconnected,
            },
        }

    if tool_name == "grafana_emqx_health":
        queries = _query_prometheus_instant_map({
            "connections":       'sum(emqx_connections_count{job="emqx"})',
            "live_connections":  'sum(emqx_live_connections_count{job="emqx"})',
            "messages_dropped":  'sum(emqx_messages_dropped{job="emqx"})',
            "delivery_dropped":  'sum(emqx_delivery_dropped{job="emqx"})',
            "auth_failure":      'sum(emqx_authentication_failure{job="emqx"})',
            "auth_deny":         'sum(emqx_authorization_deny{job="emqx"})',
            "subscriptions":     'sum(emqx_subscriptions_count{job="emqx"})',
            "cpu_use":           'avg(emqx_vm_cpu_use{job="emqx"})',
            "memory_used":       'sum(emqx_vm_used_memory{job="emqx"})',
            "nodes_running":     'sum(emqx_cluster_nodes_running{job="emqx"})',
            "nodes_stopped":     'sum(emqx_cluster_nodes_stopped{job="emqx"})',
        })
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "scenario": "10a",
            "tool": tool_name,
            "queries": queries,
        }

    if tool_name == "query_emqx_connection_count":
        queries = _query_prometheus_instant_map({
            "current_connections": 'sum(emqx_connections_count{job="emqx"})',
            "max_connections": 'sum(emqx_connections_max{job="emqx"})',
            "sessions": 'sum(emqx_sessions_count{job="emqx"})',
        })
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "scenario": "10_drilldown",
            "tool": tool_name,
            "request": {},
            "expected_metrics": list(queries.keys()),
            "queries": queries,
        }

    if tool_name == "grafana_k8s_resources":
        namespace = params.get("namespace") or DEFAULT_K8S_NAMESPACE
        service = params.get("service")
        pod = params.get("pod")
        pod_filter = f',pod="{pod}"' if pod else ''
        container_filter = 'container!="",pod!=""'
        queries = {
            "pod_cpu": (
                'topk(10, sum by (pod) '
                f'(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",'
                f'{container_filter}{pod_filter}}}[5m])))'
            ),
            "pod_memory": (
                'topk(10, sum by (pod) '
                f'(container_memory_working_set_bytes{{namespace="{namespace}",'
                f'{container_filter}{pod_filter}}}))'
            ),
            "pod_restarts": (
                'topk(10, sum by (pod) '
                f'(kube_pod_container_status_restarts_total{{namespace="{namespace}"'
                f'{pod_filter}}}))'
            ),
            "pod_status": (
                'sum by (pod, phase) '
                f'(kube_pod_status_phase{{namespace="{namespace}"'
                f'{pod_filter}}})'
            ),
            "pod_waiting_reasons": (
                'sum by (pod, reason) '
                f'(kube_pod_container_status_waiting_reason{{namespace="{namespace}",'
                f'reason=~"CrashLoopBackOff|ImagePullBackOff|ErrImagePull"'
                f'{pod_filter}}})'
            ),
            "pod_last_terminated_reasons": (
                'sum by (pod, reason) '
                f'(kube_pod_container_status_last_terminated_reason{{namespace="{namespace}",'
                f'reason=~"OOMKilled|Error"'
                f'{pod_filter}}})'
            ),
            "node_cpu": (
                '100 - (avg by (instance) '
                '(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
            ),
            "node_memory": (
                '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
            ),
        }
        results = _query_prometheus_instant_map(queries)
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "scenario": "12",
            "tool": tool_name,
            "request": {
                "namespace": namespace,
                "service": service,
                "pod": pod,
            },
            "expected_metrics": list(queries.keys()),
            "queries": results,
        }

    if tool_name == "grafana_k8s_health":
        queries = {
            "cluster_cpu_percent": (
                '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
            ),
            "cluster_memory_percent": (
                '(1 - sum(node_memory_MemAvailable_bytes) / '
                'sum(node_memory_MemTotal_bytes)) * 100'
            ),
            "pod_restarts": (
                'sum(kube_pod_container_status_restarts_total{namespace="one-iot"})'
            ),
            "pod_status": (
                'sum by (phase) (kube_pod_status_phase{namespace="one-iot"})'
            ),
        }
        results = _query_prometheus_instant_map(queries)
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "tool": tool_name,
            "request": {"namespace": DEFAULT_K8S_NAMESPACE},
            "expected_metrics": list(queries.keys()),
            "queries": results,
        }

    if tool_name == "grafana_linux_health":
        queries = {
            "cpu_percent": (
                '100 - (avg by (instance) '
                '(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
            ),
            "memory_percent": (
                '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
            ),
            "disk_percent": (
                '100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / '
                'node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})'
            ),
            "network_rx_rate": 'rate(node_network_receive_bytes_total[5m])',
        }
        results = _query_prometheus_instant_map(queries)
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "tool": tool_name,
            "request": {},
            "expected_metrics": list(queries.keys()),
            "queries": results,
        }

    if tool_name == "grafana_redis_health":
        queries = {
            "connected_clients": "redis_connected_clients",
            "ops_rate": "rate(redis_commands_processed_total[5m])",
            "hit_rate_percent": (
                '100 * redis_keyspace_hits_total / '
                '(redis_keyspace_hits_total + redis_keyspace_misses_total)'
            ),
            "memory_used_percent": (
                '100 * redis_memory_used_bytes / redis_memory_max_bytes'
            ),
        }
        results = _query_prometheus_instant_map(queries)
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "tool": tool_name,
            "request": {},
            "expected_metrics": list(queries.keys()),
            "queries": results,
        }

    if tool_name == "grafana_mongodb_health":
        queries = {
            "up": "mongodb_up",
            "connections": "mongodb_connections{state=\"current\"}",
            "ops_rate": "rate(mongodb_op_counters_total[5m])",
            "latency": "rate(mongodb_op_latencies_latency_total[5m])",
        }
        results = _query_prometheus_instant_map(queries)
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "tool": tool_name,
            "request": {},
            "expected_metrics": list(queries.keys()),
            "queries": results,
        }

    if tool_name == "grafana_mysql_health":
        queries = {
            "up": "mysql_up",
            "qps": "rate(mysql_global_status_queries[5m])",
            "threads_connected": "mysql_global_status_threads_connected",
            "slow_queries": "rate(mysql_global_status_slow_queries[5m])",
        }
        results = _query_prometheus_instant_map(queries)
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "tool": tool_name,
            "request": {},
            "expected_metrics": list(queries.keys()),
            "queries": results,
        }

    if tool_name == "grafana_http_health":
        queries = {
            "request_rate": 'sum(rate(http_server_request_duration_seconds_count{job="iot-http-api"}[5m]))',
            "error_rate_percent": '100 * sum(rate(http_server_request_duration_seconds_count{job="iot-http-api", http_response_status_code=~"5.."}[5m])) / clamp_min(sum(rate(http_server_request_duration_seconds_count{job="iot-http-api"}[5m])), 1)',
            "success_rate_percent": '100 - (100 * sum(rate(http_server_request_duration_seconds_count{job="iot-http-api", http_response_status_code=~"5.."}[5m])) / clamp_min(sum(rate(http_server_request_duration_seconds_count{job="iot-http-api"}[5m])), 1))',
            "latency_p95_ms": '1000 * histogram_quantile(0.95, sum(rate(http_server_request_duration_seconds_bucket{job="iot-http-api"}[5m])) by (le))',
        }
        results = _query_prometheus_instant_map(queries)
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "tool": tool_name,
            "request": {},
            "expected_metrics": list(queries.keys()),
            "queries": results,
        }

    if tool_name == "grafana_throughput":
        queries = {
            "publish_rate": 'sum(rate(rabbitmq_global_messages_confirmed_total{job="monitoring/rabbitmq"}[5m]))',
            "ack_rate": 'sum(rate(rabbitmq_global_messages_acknowledged_total{job="monitoring/rabbitmq"}[5m]))',
            "delivery_rate": 'sum(rate(rabbitmq_global_messages_delivered_total{job="monitoring/rabbitmq"}[5m]))',
            "queue_depth": 'sum(rabbitmq_queue_messages{job="monitoring/rabbitmq"})',
        }
        results = _query_prometheus_instant_map(queries)
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_query",
            "tool": tool_name,
            "request": {},
            "expected_metrics": list(queries.keys()),
            "queries": results,
        }

    raise ValueError(f"Unsupported MCP metric tool: {tool_name}")


def _loki_query_chunk(datasource_uid, start, end, service_name, namespace, contains, limit):
    return _call_mcp_tool_with_retries(
        "loki_query_range",
        {
            "datasource_uid": datasource_uid,
            "start": start,
            "end": end,
            "service_name": service_name,
            "namespace": namespace,
            "contains": contains,
            "limit": limit,
        },
    )


def _loki_result_is_empty(result):
    if not result:
        return True
    if isinstance(result, list):
        return len(result) == 0
    if isinstance(result, dict):
        for key in ("data", "result", "logs", "entries"):
            val = result.get(key)
            if isinstance(val, list) and len(val) > 0:
                return False
            if isinstance(val, dict):
                inner = val.get("result") or []
                if isinstance(inner, list) and len(inner) > 0:
                    return False
    return True


def query_loki_logs_via_mcp(
    *,
    service_name=None,
    namespace=DEFAULT_LOKI_NAMESPACE,
    contains=None,
    hours_back=6,
    limit=50,
):
    try:
        datasource_uid = _find_datasource_uid("loki")
    except Exception as exc:
        return {
            "source": "mcp_server",
            "mcp_tool": "grafana_list_datasources",
            "level": "unavailable",
            "error": str(exc),
            "logs": [],
        }

    if not datasource_uid:
        return {
            "source": "mcp_server",
            "mcp_tool": "loki_query_range",
            "level": "unavailable",
            "error": "No Loki datasource was found through MCP Grafana datasource discovery.",
            "logs": [],
        }

    safe_hours = _coerce_positive_int(hours_back, 6, 72)
    safe_limit = _coerce_positive_int(limit, 50, 500)
    ns = namespace or DEFAULT_LOKI_NAMESPACE
    now = int(time.time())
    full_start = now - safe_hours * 3600

    try:
        result = _loki_query_chunk(
            datasource_uid,
            full_start,
            now,
            service_name,
            ns,
            contains,
            safe_limit,
        )
        return {
            "source": "mcp_server",
            "mcp_tool": "loki_query_range",
            "request": {
                "namespace": ns,
                "service_name": service_name,
                "contains": contains,
                "hours_back": safe_hours,
                "limit": safe_limit,
            },
            "result": result,
        }
    except Exception as exc:
        full_window_error = exc

    # Fallback to a small number of recent chunks only when the full-window
    # query fails. This avoids turning one diagnostic into many MCP sessions.
    max_chunks = _coerce_positive_int(
        os.getenv("MCP_LOKI_FALLBACK_CHUNKS"),
        2,
        safe_hours,
    )
    last_error = None
    had_success = False
    for chunk_idx in range(max_chunks):
        time.sleep(1.0)
        chunk_end = now - chunk_idx * 3600
        chunk_start = chunk_end - 3600
        try:
            result = _loki_query_chunk(
                datasource_uid, chunk_start, chunk_end,
                service_name, ns, contains, safe_limit,
            )
            had_success = True
            if not _loki_result_is_empty(result):
                return {
                    "source": "mcp_server",
                    "mcp_tool": "loki_query_range",
                    "request": {
                        "namespace": ns,
                        "service_name": service_name,
                        "contains": contains,
                        "hours_back": safe_hours,
                        "chunk_hours_back": chunk_idx + 1,
                        "fallback_after_full_window_error": True,
                        "limit": safe_limit,
                    },
                    "result": result,
                }
        except Exception as exc:
            last_error = exc
            continue

    if last_error and not had_success:
        return {
            "source": "mcp_server",
            "mcp_tool": "loki_query_range",
            "level": "unavailable",
            "error": str(last_error or full_window_error),
            "request": {
                "namespace": ns,
                "service_name": service_name,
                "contains": contains,
                "hours_back": safe_hours,
                "fallback_chunks": max_chunks,
                "limit": safe_limit,
            },
            "logs": [],
        }

    # Full-window query failed, but fallback chunks succeeded and returned no
    # matching entries. Report the partial search boundary explicitly.
    return {
        "source": "mcp_server",
        "mcp_tool": "loki_query_range",
        "request": {
            "namespace": ns,
            "service_name": service_name,
            "contains": contains,
            "hours_back": safe_hours,
            "searched_recent_chunks": max_chunks,
            "fallback_after_full_window_error": True,
            "limit": safe_limit,
        },
        "result": [],
    }
