import os
import tempfile
import unittest


os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("ENABLE_EMBEDDED_TELEMETRY", "false")
os.environ.setdefault("ENABLE_MONGODB", "false")
os.environ.setdefault("READ_TELEMETRY_FROM_MONGO", "false")
os.environ.setdefault("TELEMETRY_WRITE_BACKEND", "sqlite")
os.environ["APP_DB_BACKEND"] = "sqlite"

_TEMP_DIR = tempfile.TemporaryDirectory()
_ORIGINAL_CWD = os.getcwd()
os.chdir(_TEMP_DIR.name)

import app as app_module  # noqa: E402
from relational_store import (  # noqa: E402
    add_message,
    create_chat,
    create_user,
    get_messages,
    init_db,
    verify_user,
)


class SecurityAndRealtimeTests(unittest.TestCase):
    def setUp(self):
        init_db()
        app_module.app.config["TESTING"] = True
        app_module.diagnose_rate_limit_log.clear()
        self.client = app_module.app.test_client()

    def create_user_once(self, username, password):
        try:
            create_user(username, password)
        except Exception:
            pass

        return verify_user(username, password)

    def login_as(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user["id"]
            session["username"] = user["username"]

    def test_sensitive_routes_require_login(self):
        routes = [
            ("post", "/api/diagnose", {"json": {"message": "hello"}}),
            ("post", "/api/diagnose-stream", {"json": {"message": "hello"}}),
            ("get", "/api/devices", {}),
            ("get", "/api/telemetry/sensor-001", {}),
            ("get", "/api/mongo/telemetry/health", {}),
            ("get", "/api/mongo/telemetry/indexes", {}),
            ("post", "/api/mongo/telemetry/indexes", {}),
            ("get", "/api/mongo/devices", {}),
            ("get", "/api/mongo/telemetry/sensor-001", {}),
        ]

        for method, path, kwargs in routes:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401)

    def test_chat_messages_require_owner(self):
        owner = self.create_user_once("owner", "owner-pass")
        other = self.create_user_once("other", "other-pass")
        chat_id = create_chat(owner["id"], "Private chat")
        add_message(chat_id, "user", "private message")

        self.login_as(other)

        response = self.client.get(f"/api/chats/{chat_id}/messages")
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            f"/api/chats/{chat_id}/messages",
            json={"role": "user", "content": "not mine"},
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.delete(f"/api/chats/{chat_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(get_messages(chat_id)[0]["content"], "private message")

        self.login_as(owner)

        response = self.client.get(f"/api/chats/{chat_id}/messages")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["messages"][0]["content"],
            "private message",
        )

    def test_diagnose_limits_are_enforced(self):
        user = self.create_user_once("limit-user", "limit-pass")
        self.login_as(user)

        original_max_chars = app_module.MAX_DIAGNOSE_MESSAGE_CHARS
        original_limit = app_module.DIAGNOSE_RATE_LIMIT_REQUESTS
        original_window = app_module.DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS

        app_module.MAX_DIAGNOSE_MESSAGE_CHARS = 10
        app_module.DIAGNOSE_RATE_LIMIT_REQUESTS = 2
        app_module.DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS = 60

        try:
            response = self.client.post(
                "/api/diagnose",
                json={"message": "x" * 11},
            )
            self.assertEqual(response.status_code, 413)

            response = self.client.post(
                "/api/diagnose-stream",
                json={"message": "x" * 11},
            )
            self.assertEqual(response.status_code, 413)

            response = self.client.post(
                "/api/diagnose",
                json={"message": "x" * 11},
            )
            self.assertEqual(response.status_code, 429)
            self.assertTrue(response.headers.get("Retry-After"))
        finally:
            app_module.MAX_DIAGNOSE_MESSAGE_CHARS = original_max_chars
            app_module.DIAGNOSE_RATE_LIMIT_REQUESTS = original_limit
            app_module.DIAGNOSE_RATE_LIMIT_WINDOW_SECONDS = original_window

    def test_embedded_telemetry_payload_reports_connected(self):
        app_module.generate_telemetry_batch()
        payload = app_module.build_device_update_payload()

        self.assertEqual(len(payload["devices"]), len(app_module.DEVICES))
        self.assertEqual(
            payload["alerts"]["telemetry_stream_status"],
            "connected",
        )
        self.assertLess(payload["alerts"]["telemetry_age_seconds"], 90)


def tearDownModule():
    os.chdir(_ORIGINAL_CWD)
    _TEMP_DIR.cleanup()


if __name__ == "__main__":
    unittest.main()
