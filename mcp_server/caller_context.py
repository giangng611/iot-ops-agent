def get_current_caller_id(mcp):
    ctx = mcp.get_context()
    request_context = ctx.request_context

    if request_context is None or request_context.request is None:
        return "unknown"

    return getattr(request_context.request.state, "mcp_caller_id", "unknown")
