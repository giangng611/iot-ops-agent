import hashlib
import hmac
import json
import os

from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.rate_limit import McpRateLimitError, check_rate_limit
from mcp_server.services.company_mongo_proxy import SlidingWindowRateLimiter

mcp_caller_rate_limiter = SlidingWindowRateLimiter()


def _positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


def _hash_key(raw_key):
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def get_configured_caller_keys():
    raw = os.getenv("MCP_API_KEYS_JSON", "").strip()

    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(
            "MCP_API_KEYS_JSON is not valid JSON."
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(
            "MCP_API_KEYS_JSON must be a JSON object of caller_id -> key_hash."
        )

    return parsed


def resolve_caller_id(bearer_token):
    if not bearer_token:
        return None

    presented_hash = _hash_key(bearer_token)
    caller_keys = get_configured_caller_keys()

    for caller_id, expected_hash in caller_keys.items():
        if hmac.compare_digest(presented_hash, expected_hash):
            return caller_id

    return None


def check_caller_rate_limit(caller_id):
    requests = _positive_int_env("MCP_RATE_LIMIT_REQUESTS", 60)
    window_seconds = _positive_int_env("MCP_RATE_LIMIT_WINDOW_SECONDS", 60)
    mcp_caller_rate_limiter.requests = requests
    mcp_caller_rate_limiter.window_seconds = window_seconds
    check_rate_limit(mcp_caller_rate_limiter, caller_id, "MCP API key")


class BearerAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            response = JSONResponse(
                {"error": "Missing or invalid Authorization header."},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        bearer_token = auth_header[len("Bearer "):].strip()
        caller_id = resolve_caller_id(bearer_token)

        if caller_id is None:
            response = JSONResponse(
                {"error": "Invalid MCP API key."},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        try:
            check_caller_rate_limit(caller_id)
        except McpRateLimitError as exc:
            response = JSONResponse(
                {"error": str(exc), "retry_after": exc.retry_after},
                status_code=429,
            )
            await response(scope, receive, send)
            return

        scope["state"] = scope.get("state", {})
        scope["state"]["mcp_caller_id"] = caller_id
        await self.app(scope, receive, send)
