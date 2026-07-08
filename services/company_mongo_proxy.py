import os
import threading
import time
from pathlib import Path
from collections import defaultdict, deque
from urllib.parse import parse_qs, urlparse

from pymongo import MongoClient

from services.mcp_client import McpClientError, SyncMcpToolSession, call_mcp_tool


DEFAULT_RATE_LIMIT_REQUESTS = 120
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
MAX_QUERY_LIMIT = 1000
DEFAULT_ALLOWED_NAMESPACES = frozenset({
    "authorization.IDENTITY",
    "subNNotif.AE",
    "subNNotif.SUB",
    "datamgmt.CIN",
    "datamgmt.CNT",
    "datamgmt.DEVICE_TELEMETRY",
    "datamgmt.RULE",
    "devicemgmt.NODE",
    "orchestration.URI_MAPPER",
})
IDENTIFIER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
BLOCKED_QUERY_OPERATORS = {
    "$accumulator",
    "$expr",
    "$function",
    "$geoNear",
    "$jsonSchema",
    "$merge",
    "$near",
    "$nearSphere",
    "$out",
    "$regex",
    "$text",
    "$where",
}
ALLOWED_SORT_DIRECTIONS = {-1, 1}


class CompanyMongoProxyRateLimitError(RuntimeError):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__(
            "Company MongoDB read proxy rate limit exceeded. "
            f"Retry after {retry_after} seconds."
        )


def _positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


def _validate_identifier(value, label):
    if (
        not isinstance(value, str)
        or not value
        or any(character not in IDENTIFIER_CHARS for character in value)
    ):
        raise ValueError(f"Invalid MongoDB {label}: {value}")


def _validate_read_document(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key in BLOCKED_QUERY_OPERATORS:
                raise ValueError(
                    f"MongoDB query operator is not allowed: {key}"
                )
            _validate_read_document(nested_value)
    elif isinstance(value, (list, tuple)):
        for nested_value in value:
            _validate_read_document(nested_value)


def _validate_sort(sort):
    if sort is None:
        return

    if (
        not isinstance(sort, (list, tuple))
        or len(sort) != 2
    ):
        raise ValueError("MongoDB sort must be a (field, direction) pair.")

    field, direction = sort
    _validate_identifier(field, "sort field")

    if direction not in ALLOWED_SORT_DIRECTIONS:
        raise ValueError("MongoDB sort direction must be 1 or -1.")


def _mongo_seed_hosts(uri):
    parsed = urlparse(uri or "")
    netloc = parsed.netloc.rsplit("@", 1)[-1]

    return [
        seed.strip()
        for seed in netloc.split(",")
        if seed.strip()
    ]


def _mongo_query_options(uri):
    parsed = urlparse(uri or "")
    return {
        key.lower(): values
        for key, values in parse_qs(parsed.query).items()
    }


def should_use_direct_connection(uri):
    options = _mongo_query_options(uri)

    if any(
        option in options
        for option in ("directconnection", "replicaset", "loadbalanced")
    ):
        return False

    return len(_mongo_seed_hosts(uri)) == 1


def get_allowed_namespaces():
    configured = os.getenv("COMPANY_MONGO_ALLOWED_NAMESPACES", "").strip()

    if not configured:
        return DEFAULT_ALLOWED_NAMESPACES

    namespaces = {
        namespace.strip()
        for namespace in configured.split(",")
        if namespace.strip()
    }

    for namespace in namespaces:
        if namespace.count(".") != 1:
            raise ValueError(
                "Company MongoDB namespaces must use database.collection "
                f"format: {namespace}"
            )

        database_name, collection_name = namespace.split(".", 1)
        _validate_identifier(database_name, "database name")
        _validate_identifier(collection_name, "collection name")

    return frozenset(namespaces)


class SlidingWindowRateLimiter:
    def __init__(self, requests=None, window_seconds=None, clock=None):
        self.requests = requests
        self.window_seconds = window_seconds
        self.clock = clock or time.monotonic
        self._request_log = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key):
        requests = self.requests or _positive_int_env(
            "COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS",
            DEFAULT_RATE_LIMIT_REQUESTS,
        )
        window_seconds = self.window_seconds or _positive_int_env(
            "COMPANY_MONGO_PROXY_RATE_LIMIT_WINDOW_SECONDS",
            DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        )
        now = self.clock()
        window_start = now - window_seconds

        with self._lock:
            request_times = self._request_log[key]

            while request_times and request_times[0] <= window_start:
                request_times.popleft()

            if len(request_times) >= requests:
                retry_after = max(
                    1,
                    int(window_seconds - (now - request_times[0])),
                )
                raise CompanyMongoProxyRateLimitError(retry_after)

            request_times.append(now)

    def clear(self):
        with self._lock:
            self._request_log.clear()


company_mongo_rate_limiter = SlidingWindowRateLimiter()


class CompanyMongoReadProxy:
    def __init__(self, uri, actor="company-data-service", client_factory=None):
        if not uri:
            raise RuntimeError("Company MongoDB URI is not configured.")

        timeout_ms = _positive_int_env(
            "COMPANY_DB_CONNECT_TIMEOUT_SECONDS",
            5,
        ) * 1000
        statement_timeout_ms = _positive_int_env(
            "COMPANY_DB_STATEMENT_TIMEOUT_MS",
            5000,
        )
        factory = client_factory or MongoClient
        self._actor = actor
        self._statement_timeout_ms = statement_timeout_ms
        self._audit_events = []
        client_kwargs = {
            "serverSelectionTimeoutMS": timeout_ms,
            "connectTimeoutMS": timeout_ms,
            "socketTimeoutMS": statement_timeout_ms,
        }

        if should_use_direct_connection(uri):
            client_kwargs["directConnection"] = True

        self._client = factory(
            uri,
            **client_kwargs,
        )
        self._client.admin.command("ping")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self._client.close()

    def get_audit_events(self):
        return list(self._audit_events)

    def _audit_read(
        self,
        *,
        operation,
        database_name,
        collection_name=None,
        query=None,
        projection=None,
        sort=None,
        requested_limit=None,
        effective_limit=None,
    ):
        namespace = (
            f"{database_name}.{collection_name}"
            if collection_name
            else database_name
        )
        self._audit_events.append({
            "actor": self._actor,
            "operation": operation,
            "namespace": namespace,
            "query": query or {},
            "projection": projection or {},
            "sort": sort,
            "requested_limit": requested_limit,
            "effective_limit": effective_limit,
            "max_time_ms": self._statement_timeout_ms,
            "allowed_namespaces_enforced": True,
            "blocked_operators": sorted(BLOCKED_QUERY_OPERATORS),
            "credentials_redacted": True,
            "mutating": False,
        })

    def _check_read(self, operation, database_name, collection_name=None):
        _validate_identifier(database_name, "database name")

        if collection_name is not None:
            _validate_identifier(collection_name, "collection name")
            namespace = f"{database_name}.{collection_name}"

            if namespace not in get_allowed_namespaces():
                raise PermissionError(
                    f"Company MongoDB namespace is not allowed: {namespace}"
                )

        company_mongo_rate_limiter.check(
            f"{self._actor}:{operation}"
        )

    def list_database_names(self):
        company_mongo_rate_limiter.check(
            f"{self._actor}:list_database_names"
        )
        allowed_databases = {
            namespace.split(".", 1)[0]
            for namespace in get_allowed_namespaces()
        }
        databases = [
            database_name
            for database_name in self._client.list_database_names()
            if database_name in allowed_databases
        ]
        self._audit_read(
            operation="list_database_names",
            database_name="*",
            effective_limit=len(databases),
        )
        return databases

    def list_collections(self, database_name):
        self._check_read("list_collections", database_name)
        allowed_collections = {
            namespace.split(".", 1)[1]
            for namespace in get_allowed_namespaces()
            if namespace.startswith(f"{database_name}.")
        }
        collections = [
            namespace
            for namespace in self._client[database_name].list_collections(
            filter={"type": {"$in": ["collection", "view"]}},
            nameOnly=True,
            )
            if namespace.get("name") in allowed_collections
        ]
        self._audit_read(
            operation="list_collections",
            database_name=database_name,
            query={"type": {"$in": ["collection", "view"]}},
            projection={"nameOnly": True},
            effective_limit=len(collections),
        )
        return collections

    def collection_stats(self, database_name, collection_name):
        self._check_read(
            "collection_stats",
            database_name,
            collection_name,
        )
        stats = self._client[database_name].command(
            "collStats",
            collection_name,
            scale=1,
            maxTimeMS=self._statement_timeout_ms,
        )
        self._audit_read(
            operation="collStats",
            database_name=database_name,
            collection_name=collection_name,
            query={"command": "collStats", "scale": 1},
            effective_limit=1,
        )
        return stats

    def find(
        self,
        database_name,
        collection_name,
        query=None,
        projection=None,
        sort=None,
        limit=100,
    ):
        self._check_read("find", database_name, collection_name)
        query = query or {}
        _validate_read_document(query)
        _validate_read_document(projection or {})
        _validate_sort(sort)
        safe_limit = max(1, min(int(limit), MAX_QUERY_LIMIT))
        self._audit_read(
            operation="find",
            database_name=database_name,
            collection_name=collection_name,
            query=query,
            projection=projection,
            sort=sort,
            requested_limit=limit,
            effective_limit=safe_limit,
        )
        cursor = self._client[database_name][collection_name].find(
            query,
            projection,
        )

        if sort:
            cursor = cursor.sort(*sort)

        return list(
            cursor
            .max_time_ms(self._statement_timeout_ms)
            .limit(safe_limit)
        )


class MCPCompanyMongoReadProxy:
    def __init__(self, actor="company-data-service", tool_caller=None):
        self._actor = actor
        self._tool_caller = tool_caller or call_mcp_tool
        self._custom_tool_caller = tool_caller is not None
        self._session = None
        self._audit_events = []

    def __enter__(self):
        if not self._custom_tool_caller:
            self._open_session()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self._session is not None:
            self._session.__exit__(None, None, None)
            self._session = None

        return None

    def _open_session(self):
        self._session = SyncMcpToolSession()
        self._session.__enter__()
        self._tool_caller = self._session.call_tool

    def _reopen_session(self):
        self.close()
        self._open_session()

    def _is_retryable_mcp_error(self, exc):
        if not isinstance(exc, McpClientError):
            return False

        message = str(exc).lower()
        retryable_fragments = (
            "failed before tool result",
            "taskgroup",
            "timed out",
            "connection",
        )
        return any(fragment in message for fragment in retryable_fragments)

    def _call_mcp_read_tool(self, tool_name, arguments):
        attempts = 3

        for attempt in range(attempts):
            try:
                return self._tool_caller(tool_name, arguments)
            except Exception as exc:
                if attempt >= attempts - 1 or not self._is_retryable_mcp_error(exc):
                    raise

                if not self._custom_tool_caller:
                    self._reopen_session()

                time.sleep(0.2 * (attempt + 1))

    def get_audit_events(self):
        return list(self._audit_events)

    def _audit_mcp_call(
        self,
        *,
        operation,
        database_name=None,
        collection_name=None,
        query=None,
        projection=None,
        sort=None,
        requested_limit=None,
    ):
        namespace = (
            f"{database_name}.{collection_name}"
            if database_name and collection_name
            else database_name or "*"
        )
        self._audit_events.append({
            "actor": self._actor,
            "operation": operation,
            "namespace": namespace,
            "query": query or {},
            "projection": projection or {},
            "sort": sort,
            "requested_limit": requested_limit,
            "access_path": "mcp_server",
            "credentials_redacted": True,
            "mutating": False,
        })

    def list_database_names(self):
        self._audit_mcp_call(operation="list_database_names")
        return self._call_mcp_read_tool("mongo_list_databases", {})

    def list_collections(self, database_name):
        self._audit_mcp_call(
            operation="list_collections",
            database_name=database_name,
        )
        collections = self._call_mcp_read_tool(
            "mongo_list_collections",
            {"database": database_name},
        )

        return [
            (
                {"name": collection_name, "type": "collection"}
                if isinstance(collection_name, str)
                else collection_name
            )
            for collection_name in collections
        ]

    def collection_stats(self, database_name, collection_name):
        self._audit_mcp_call(
            operation="collStats",
            database_name=database_name,
            collection_name=collection_name,
        )
        return self._call_mcp_read_tool(
            "mongo_collection_stats",
            {
                "database": database_name,
                "collection": collection_name,
            },
        )

    def find(
        self,
        database_name,
        collection_name,
        query=None,
        projection=None,
        sort=None,
        limit=100,
    ):
        query = query or {}
        projection = projection or None
        sort_field = sort[0] if sort else None
        sort_direction = sort[1] if sort else None
        self._audit_mcp_call(
            operation="find",
            database_name=database_name,
            collection_name=collection_name,
            query=query,
            projection=projection,
            sort=sort,
            requested_limit=limit,
        )
        return self._call_mcp_read_tool(
            "mongo_find",
            {
                "database": database_name,
                "collection": collection_name,
                "query": query,
                "projection": projection,
                "sort_field": sort_field,
                "sort_direction": sort_direction,
                "limit": limit,
            },
        )


def company_data_access_mode():
    return os.getenv("COMPANY_DATA_ACCESS_MODE", "direct").strip().lower()


def _read_env_file_value(path, key):
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()

            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            name, value = stripped.split("=", 1)

            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except OSError:
        return ""

    return ""


def get_company_mongo_direct_uri(include_mcp_server_env=False):
    uri = (
        os.getenv("COMPANY_MONGODB_URI")
        or os.getenv("COMPANY_MONGO_URI")
        or os.getenv("IOT_PLATFORM_MONGODB_URI")
    )

    if uri or not include_mcp_server_env:
        return uri

    return _read_env_file_value("mcp_server/.env", "COMPANY_MONGODB_URI")


def get_company_mongo_read_proxy(actor="company-data-service", force_direct=False):
    if company_data_access_mode() == "mcp" and not force_direct:
        return MCPCompanyMongoReadProxy(actor=actor)

    uri = get_company_mongo_direct_uri(include_mcp_server_env=force_direct)
    return CompanyMongoReadProxy(uri, actor=actor)
