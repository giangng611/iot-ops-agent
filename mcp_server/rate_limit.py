from mcp_server.services.company_mongo_proxy import CompanyMongoProxyRateLimitError


class McpRateLimitError(RuntimeError):
    def __init__(self, context_label, retry_after):
        self.retry_after = retry_after
        super().__init__(
            f"{context_label} rate limit exceeded. Retry after {retry_after} seconds."
        )


def check_rate_limit(limiter, key, context_label):
    """Run limiter.check(key), translating the Mongo-proxy-flavored error
    raised by the shared SlidingWindowRateLimiter into one labeled for the
    actual caller (MCP auth, Loki, Grafana), since the limiter is generic
    but its exception type/message is not.
    """
    try:
        limiter.check(key)
    except CompanyMongoProxyRateLimitError as exc:
        raise McpRateLimitError(context_label, exc.retry_after) from exc
