from typing import Any

from mcp_server.audit_log import log_tool_call
from mcp_server.caller_context import get_current_caller_id
from mcp_server.services.mongo_proxy_pool import get_pooled_mongo_proxy


def register_mongo_tools(mcp):
    @mcp.tool()
    def mongo_find(
        database: str,
        collection: str,
        query: dict | None = None,
        projection: dict | None = None,
        sort_field: str | None = None,
        sort_direction: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read documents from an allowlisted company MongoDB namespace."""
        caller_id = get_current_caller_id(mcp)
        sort = (sort_field, sort_direction) if sort_field else None
        proxy = get_pooled_mongo_proxy()

        try:
            results = proxy.find(
                database,
                collection,
                query=query,
                projection=projection,
                sort=sort,
                limit=limit,
            )
            log_tool_call(caller_id, "mongo_find", proxy.get_audit_events())
            return results
        except Exception as exc:
            log_tool_call(caller_id, "mongo_find", error=exc)
            raise

    @mcp.tool()
    def mongo_list_collections(database: str) -> list[str]:
        """List allowlisted collections in a company MongoDB database."""
        caller_id = get_current_caller_id(mcp)
        proxy = get_pooled_mongo_proxy()

        try:
            results = proxy.list_collections(database)
            log_tool_call(caller_id, "mongo_list_collections", proxy.get_audit_events())
            return results
        except Exception as exc:
            log_tool_call(caller_id, "mongo_list_collections", error=exc)
            raise

    @mcp.tool()
    def mongo_collection_stats(database: str, collection: str) -> dict[str, Any]:
        """Get collection stats for an allowlisted company MongoDB collection."""
        caller_id = get_current_caller_id(mcp)
        proxy = get_pooled_mongo_proxy()

        try:
            results = proxy.collection_stats(database, collection)
            log_tool_call(caller_id, "mongo_collection_stats", proxy.get_audit_events())
            return results
        except Exception as exc:
            log_tool_call(caller_id, "mongo_collection_stats", error=exc)
            raise

    @mcp.tool()
    def mongo_list_databases() -> list[str]:
        """List allowlisted company MongoDB databases."""
        caller_id = get_current_caller_id(mcp)
        proxy = get_pooled_mongo_proxy()

        try:
            results = proxy.list_database_names()
            log_tool_call(caller_id, "mongo_list_databases", proxy.get_audit_events())
            return results
        except Exception as exc:
            log_tool_call(caller_id, "mongo_list_databases", error=exc)
            raise
