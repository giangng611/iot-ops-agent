import json
import logging
import sys
import time

logger = logging.getLogger("mcp_server.audit")
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)


def log_tool_call(caller_id, tool_name, audit_events=None, error=None):
    record = {
        "ts": time.time(),
        "caller_id": caller_id,
        "tool": tool_name,
        "audit_events": audit_events or [],
        "error": str(error) if error else None,
    }
    logger.info(json.dumps(record, default=str))
