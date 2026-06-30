from typing import Any

from grafana_client.model import DatasourceIdentifier

from mcp_server.audit_log import log_tool_call
from mcp_server.caller_context import get_current_caller_id
from mcp_server.services.grafana_client_factory import get_pooled_grafana_client


def register_grafana_tools(mcp):
    @mcp.tool()
    def grafana_list_datasources() -> list[dict[str, Any]]:
        """List datasources configured in Grafana (id, uid, name, type)."""
        caller_id = get_current_caller_id(mcp)
        grafana = get_pooled_grafana_client()

        try:
            results = grafana.datasource.list_datasources()
            log_tool_call(caller_id, "grafana_list_datasources")
            return results
        except Exception as exc:
            log_tool_call(caller_id, "grafana_list_datasources", error=exc)
            raise

    @mcp.tool()
    def grafana_query(datasource_uid: str, promql_query: str) -> dict[str, Any]:
        """Run an instant PromQL query against a Grafana Prometheus datasource."""
        caller_id = get_current_caller_id(mcp)
        grafana = get_pooled_grafana_client()

        try:
            results = grafana.datasource.smartquery(
                DatasourceIdentifier(uid=datasource_uid),
                promql_query,
                attrs={"queryType": "instant"},
            )
            log_tool_call(caller_id, "grafana_query", {"datasource_uid": datasource_uid, "query": promql_query})
            return results
        except Exception as exc:
            log_tool_call(caller_id, "grafana_query", error=exc)
            raise

    @mcp.tool()
    def grafana_query_range(datasource_uid: str, promql_query: str, start: int, end: int, step: int = 60) -> dict[str, Any]:
        """Run a PromQL range query against a Grafana Prometheus datasource. start/end are Unix seconds."""
        caller_id = get_current_caller_id(mcp)
        grafana = get_pooled_grafana_client()

        try:
            results = grafana.datasource.smartquery(
                DatasourceIdentifier(uid=datasource_uid),
                promql_query,
                attrs={"queryType": "range", "time_from": start, "time_to": end, "step": step},
            )
            log_tool_call(
                caller_id,
                "grafana_query_range",
                {"datasource_uid": datasource_uid, "query": promql_query, "start": start, "end": end},
            )
            return results
        except Exception as exc:
            log_tool_call(caller_id, "grafana_query_range", error=exc)
            raise
