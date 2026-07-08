from typing import Any

from grafana_client.model import DatasourceIdentifier

from mcp_server.audit_log import log_tool_call
from mcp_server.caller_context import get_current_caller_id
from mcp_server.services.grafana_client_factory import get_pooled_grafana_client

DEFAULT_NAMESPACE = "one-iot"


def build_logql_selector(namespace=None, service_name=None):
    namespace = namespace or DEFAULT_NAMESPACE
    clauses = [f'k8s_namespace_name="{namespace}"']

    if service_name:
        clauses.append(f'service_name="{service_name}"')

    return "{" + ", ".join(clauses) + "}"


def _escape_logql_line_filter_value(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def register_loki_tools(mcp):
    @mcp.tool()
    def loki_query_range(
        datasource_uid: str,
        start: int,
        end: int,
        service_name: str | None = None,
        namespace: str = DEFAULT_NAMESPACE,
        contains: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Query Grafana Loki logs for a namespace (defaults to "one-iot") and
        optional service_name, over [start, end) Unix seconds. Pass `contains`
        to add a full-text line filter (LogQL `|= "..."`); combined with
        omitting service_name, this searches every service in the namespace
        at once -- useful for following a trace/correlation id across
        services without knowing which service it landed in."""
        caller_id = get_current_caller_id(mcp)
        grafana = get_pooled_grafana_client()
        logql_query = build_logql_selector(namespace=namespace, service_name=service_name)

        if contains:
            logql_query += f' |= "{_escape_logql_line_filter_value(contains)}"'

        try:
            results = grafana.datasource.smartquery(
                DatasourceIdentifier(uid=datasource_uid),
                logql_query,
                attrs={"queryType": "range", "time_from": start, "time_to": end, "maxLines": limit},
            )
            log_tool_call(
                caller_id,
                "loki_query_range",
                {"datasource_uid": datasource_uid, "query": logql_query, "start": start, "end": end},
            )
            return results
        except Exception as exc:
            log_tool_call(caller_id, "loki_query_range", error=exc)
            raise
