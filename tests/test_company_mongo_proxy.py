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


if __name__ == "__main__":
    unittest.main()
