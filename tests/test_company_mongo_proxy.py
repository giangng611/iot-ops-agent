import unittest
from unittest.mock import patch

from services.company_mongo_proxy import (
    CompanyMongoProxyRateLimitError,
    CompanyMongoReadProxy,
    SlidingWindowRateLimiter,
    company_mongo_rate_limiter,
)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sort_args = None
        self.timeout_ms = None
        self.limit_value = None

    def sort(self, *args):
        self.sort_args = args
        return self

    def max_time_ms(self, timeout_ms):
        self.timeout_ms = timeout_ms
        return self

    def limit(self, limit):
        self.limit_value = limit
        return self

    def __iter__(self):
        return iter(self.rows[:self.limit_value])


class FakeCollection:
    def __init__(self, rows):
        self.cursor = FakeCursor(rows)
        self.find_args = None

    def find(self, query, projection):
        self.find_args = (query, projection)
        return self.cursor


class FakeDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, collection_name):
        return self.collection

    def list_collections(self, **kwargs):
        return [
            {"name": "CIN", "type": "collection"},
            {"name": "SECRET", "type": "collection"},
        ]


class FakeAdmin:
    def command(self, command):
        if command != "ping":
            raise AssertionError(f"Unexpected admin command: {command}")


class FakeClient:
    def __init__(self, collection):
        self.admin = FakeAdmin()
        self.database = FakeDatabase(collection)
        self.closed = False

    def __getitem__(self, database_name):
        return self.database

    def list_database_names(self):
        return ["datamgmt", "secret", "admin"]

    def close(self):
        self.closed = True


class CompanyMongoProxyTests(unittest.TestCase):
    def setUp(self):
        company_mongo_rate_limiter.clear()

    def test_sliding_window_rate_limiter_rejects_excess_reads(self):
        now = [100.0]
        limiter = SlidingWindowRateLimiter(
            requests=2,
            window_seconds=10,
            clock=lambda: now[0],
        )

        limiter.check("llm:find")
        limiter.check("llm:find")

        with self.assertRaises(CompanyMongoProxyRateLimitError) as context:
            limiter.check("llm:find")

        self.assertEqual(context.exception.retry_after, 10)

        now[0] = 110.0
        limiter.check("llm:find")

    def test_rate_limit_environment_is_read_at_request_time(self):
        limiter = SlidingWindowRateLimiter(clock=lambda: 100.0)

        with patch.dict(
            "os.environ",
            {
                "COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS": "1",
                "COMPANY_MONGO_PROXY_RATE_LIMIT_WINDOW_SECONDS": "30",
            },
        ):
            limiter.check("llm:find")

            with self.assertRaises(CompanyMongoProxyRateLimitError):
                limiter.check("llm:find")

    def test_find_applies_timeout_sort_and_hard_limit(self):
        collection = FakeCollection([{"value": 1}, {"value": 2}])
        client = FakeClient(collection)
        proxy = CompanyMongoReadProxy(
            "mongodb://example.invalid",
            actor="test",
            client_factory=lambda *args, **kwargs: client,
        )

        rows = proxy.find(
            "datamgmt",
            "CIN",
            {"con": {"$exists": True}},
            {"_id": 0, "con": 1},
            sort=("ct", -1),
            limit=5000,
        )

        self.assertEqual(rows, [{"value": 1}, {"value": 2}])
        self.assertEqual(
            collection.find_args,
            (
                {"con": {"$exists": True}},
                {"_id": 0, "con": 1},
            ),
        )
        self.assertEqual(collection.cursor.sort_args, ("ct", -1))
        self.assertEqual(collection.cursor.limit_value, 1000)
        self.assertGreater(collection.cursor.timeout_ms, 0)
        audit_events = proxy.get_audit_events()
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(audit_events[0]["actor"], "test")
        self.assertEqual(audit_events[0]["operation"], "find")
        self.assertEqual(audit_events[0]["namespace"], "datamgmt.CIN")
        self.assertEqual(
            audit_events[0]["query"],
            {"con": {"$exists": True}},
        )
        self.assertEqual(audit_events[0]["projection"], {"_id": 0, "con": 1})
        self.assertEqual(audit_events[0]["sort"], ("ct", -1))
        self.assertEqual(audit_events[0]["requested_limit"], 5000)
        self.assertEqual(audit_events[0]["effective_limit"], 1000)
        self.assertTrue(audit_events[0]["credentials_redacted"])
        self.assertFalse(audit_events[0]["mutating"])
        self.assertFalse(hasattr(proxy, "insert_one"))
        self.assertFalse(hasattr(proxy, "update_one"))
        self.assertFalse(hasattr(proxy, "delete_one"))

    def test_find_rejects_server_side_javascript_operator(self):
        collection = FakeCollection([])
        client = FakeClient(collection)
        proxy = CompanyMongoReadProxy(
            "mongodb://example.invalid",
            actor="test",
            client_factory=lambda *args, **kwargs: client,
        )

        with self.assertRaisesRegex(ValueError, r"\$where"):
            proxy.find(
                "datamgmt",
                "CIN",
                {"$where": "function () { return true; }"},
            )

    def test_find_rejects_expensive_query_operators(self):
        collection = FakeCollection([])
        client = FakeClient(collection)
        proxy = CompanyMongoReadProxy(
            "mongodb://example.invalid",
            actor="test",
            client_factory=lambda *args, **kwargs: client,
        )

        for query in (
            {"name": {"$regex": ".*"}},
            {"$expr": {"$eq": ["$status", "critical"]}},
            {"location": {"$near": [0, 0]}},
        ):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    proxy.find("datamgmt", "CIN", query)

    def test_find_rejects_invalid_namespace_sort_and_limit(self):
        collection = FakeCollection([])
        client = FakeClient(collection)
        proxy = CompanyMongoReadProxy(
            "mongodb://example.invalid",
            actor="test",
            client_factory=lambda *args, **kwargs: client,
        )

        invalid_calls = (
            lambda: proxy.find("admin.system", "users"),
            lambda: proxy.find("datamgmt", "$cmd"),
            lambda: proxy.find("datamgmt", "CIN", sort=("$natural", 1)),
            lambda: proxy.find("datamgmt", "CIN", sort=("ct", 0)),
            lambda: proxy.find("datamgmt", "CIN", limit="unbounded"),
        )

        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call):
                with self.assertRaises((TypeError, ValueError)):
                    invalid_call()

    def test_rate_limits_are_isolated_by_actor(self):
        collection = FakeCollection([])
        client = FakeClient(collection)

        with patch.dict(
            "os.environ",
            {
                "COMPANY_MONGO_PROXY_RATE_LIMIT_REQUESTS": "1",
                "COMPANY_MONGO_PROXY_RATE_LIMIT_WINDOW_SECONDS": "60",
            },
        ):
            first_proxy = CompanyMongoReadProxy(
                "mongodb://example.invalid",
                actor="first",
                client_factory=lambda *args, **kwargs: client,
            )
            second_proxy = CompanyMongoReadProxy(
                "mongodb://example.invalid",
                actor="second",
                client_factory=lambda *args, **kwargs: client,
            )

            first_proxy.find("datamgmt", "CIN")
            second_proxy.find("datamgmt", "CIN")

            with self.assertRaises(CompanyMongoProxyRateLimitError):
                first_proxy.find("datamgmt", "CIN")

    def test_proxy_rejects_namespaces_outside_allowlist(self):
        collection = FakeCollection([])
        client = FakeClient(collection)
        proxy = CompanyMongoReadProxy(
            "mongodb://example.invalid",
            actor="test",
            client_factory=lambda *args, **kwargs: client,
        )

        with self.assertRaises(PermissionError):
            proxy.find("datamgmt", "SECRET")

        with self.assertRaises(PermissionError):
            proxy.find("admin", "system_users")

    def test_discovery_only_returns_allowlisted_namespaces(self):
        collection = FakeCollection([])
        client = FakeClient(collection)
        proxy = CompanyMongoReadProxy(
            "mongodb://example.invalid",
            actor="test",
            client_factory=lambda *args, **kwargs: client,
        )

        self.assertEqual(proxy.list_database_names(), ["datamgmt"])
        self.assertEqual(
            proxy.list_collections("datamgmt"),
            [{"name": "CIN", "type": "collection"}],
        )

    def test_namespace_allowlist_can_be_configured(self):
        collection = FakeCollection([])
        client = FakeClient(collection)
        proxy = CompanyMongoReadProxy(
            "mongodb://example.invalid",
            actor="test",
            client_factory=lambda *args, **kwargs: client,
        )

        with patch.dict(
            "os.environ",
            {"COMPANY_MONGO_ALLOWED_NAMESPACES": "custom.devices"},
        ):
            proxy.find("custom", "devices")

            with self.assertRaises(PermissionError):
                proxy.find("datamgmt", "CIN")


if __name__ == "__main__":
    unittest.main()
