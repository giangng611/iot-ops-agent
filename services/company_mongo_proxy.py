import os
import threading
import time
from collections import defaultdict, deque

from pymongo import MongoClient


DEFAULT_RATE_LIMIT_REQUESTS = 120
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
MAX_QUERY_LIMIT = 1000
DEFAULT_ALLOWED_NAMESPACES = frozenset({
    "authorization.IDENTITY",
    "datamgmt.CIN",
    "datamgmt.CNT",
    "datamgmt.DEVICE_TELEMETRY",
    "datamgmt.RULE",
    "devicemgmt.NODE",
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
        self._client = factory(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=statement_timeout_ms,
        )
        self._client.admin.command("ping")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self._client.close()

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
        return [
            database_name
            for database_name in self._client.list_database_names()
            if database_name in allowed_databases
        ]

    def list_collections(self, database_name):
        self._check_read("list_collections", database_name)
        allowed_collections = {
            namespace.split(".", 1)[1]
            for namespace in get_allowed_namespaces()
            if namespace.startswith(f"{database_name}.")
        }
        return [
            namespace
            for namespace in self._client[database_name].list_collections(
            filter={"type": {"$in": ["collection", "view"]}},
            nameOnly=True,
            )
            if namespace.get("name") in allowed_collections
        ]

    def collection_stats(self, database_name, collection_name):
        self._check_read(
            "collection_stats",
            database_name,
            collection_name,
        )
        return self._client[database_name].command(
            "collStats",
            collection_name,
            scale=1,
            maxTimeMS=self._statement_timeout_ms,
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
        self._check_read("find", database_name, collection_name)
        query = query or {}
        _validate_read_document(query)
        _validate_read_document(projection or {})
        _validate_sort(sort)
        safe_limit = max(1, min(int(limit), MAX_QUERY_LIMIT))
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


def get_company_mongo_read_proxy(actor="company-data-service"):
    uri = (
        os.getenv("COMPANY_MONGODB_URI")
        or os.getenv("COMPANY_MONGO_URI")
        or os.getenv("IOT_PLATFORM_MONGODB_URI")
    )
    return CompanyMongoReadProxy(uri, actor=actor)
