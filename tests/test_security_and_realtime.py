import os
import tempfile
import unittest
from unittest.mock import patch


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
import storage.mongo_store as mongo_store  # noqa: E402
import storage.relational_store as relational_store  # noqa: E402
from storage.relational_store import (  # noqa: E402
    add_message,
    create_chat,
    create_user,
    get_messages,
    init_db,
    verify_user,
)


class SecurityAndRealtimeTests(unittest.TestCase):
    def setUp(self):
        relational_store._last_fallback = None
        for postgres_url_var in ("SUPABASE_DB_URL", "DATABASE_URL", "POSTGRES_URL"):
            os.environ.pop(postgres_url_var, None)
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
            ("get", "/api/data-source", {}),
            ("post", "/api/data-source", {"json": {"selected_source": "company"}}),
            ("get", "/api/devices", {}),
            ("get", "/api/telemetry/sensor-001", {}),
            ("get", "/api/mongo/telemetry/health", {}),
            ("get", "/api/mongo/telemetry/indexes", {}),
            ("post", "/api/mongo/telemetry/indexes", {}),
            ("get", "/api/mongo/devices", {}),
            ("get", "/api/mongo/telemetry/sensor-001", {}),
            ("get", "/api/storage/status", {}),
            ("get", "/api/chats", {}),
            ("post", "/api/chats", {"json": {"message": "hello"}}),
            ("get", "/api/prompts", {}),
            ("post", "/api/prompts", {"json": {"title": "x", "command": "/x"}}),
            ("get", "/api/profile/usage-stats", {}),
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
        self.assertLess(
            payload["alerts"]["telemetry_age_seconds"],
            app_module.TELEMETRY_CONNECTED_GRACE_SECONDS,
        )

    def test_telemetry_routes_return_source_payloads(self):
        user = self.create_user_once("telemetry-route-user", "telemetry-pass")
        self.login_as(user)
        app_module.generate_telemetry_batch()

        response = self.client.get("/api/devices")
        self.assertEqual(response.status_code, 200)
        devices_payload = response.get_json()
        self.assertEqual(devices_payload["source"], "sqlite")
        self.assertTrue(devices_payload["devices"])
        self.assertEqual(devices_payload["selected_source"], "simulator")
        self.assertEqual(devices_payload["rules_status"], "simulator")

        response = self.client.get("/api/telemetry/sensor-001")
        self.assertEqual(response.status_code, 200)
        history_payload = response.get_json()
        self.assertEqual(history_payload["source"], "sqlite")
        self.assertEqual(history_payload["device_id"], "sensor-001")

    def test_data_source_switch_to_company_returns_rules_pending(self):
        user = self.create_user_once("company-source-user", "company-pass")
        self.login_as(user)

        company_payload = {
            "source": "company_mongodb",
            "selected_source": "company",
            "active_source": "company_mongodb",
            "rules_status": "not_configured",
            "rules_message": "Company alert rules are not configured yet.",
            "devices": [
                {
                    "device_id": "cin-record-1",
                    "status": "unknown",
                    "cpu_usage": None,
                    "memory_usage": None,
                    "heartbeat_delay": None,
                    "timestamp": 20260608,
                    "company_record": True,
                    "rules_status": "not_configured",
                    "payload_summary": {
                        "payload_type": "json",
                        "fields": ["temperature"],
                    },
                }
            ],
            "alerts": {
                "critical_count": 0,
                "warning_count": 0,
                "rules_status": "not_configured",
            },
        }

        with patch(
            "services.telemetry_service.get_company_operational_payload",
            return_value=company_payload,
        ):
            response = self.client.post(
                "/api/data-source",
                json={"selected_source": "company"},
            )
            self.assertEqual(response.status_code, 200)

            response = self.client.get("/api/devices")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()

        self.assertEqual(payload["source"], "company_mongodb")
        self.assertEqual(payload["selected_source"], "company")
        self.assertEqual(payload["rules_status"], "not_configured")
        self.assertEqual(payload["alerts"]["critical_count"], 0)
        self.assertEqual(payload["alerts"]["warning_count"], 0)
        self.assertTrue(payload["devices"][0]["company_record"])

    def test_profile_usage_stats_include_storage_status(self):
        user = self.create_user_once("storage-status-user", "storage-pass")
        self.login_as(user)

        response = self.client.get("/api/profile/usage-stats")
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(
            payload["storage"]["app_data"]["active_backend"],
            "sqlite",
        )
        self.assertFalse("error" in payload["storage"]["app_data"])
        self.assertEqual(payload["storage"]["telemetry"]["source"], "sqlite")

    def test_prompt_crud_routes_use_authenticated_user(self):
        user = self.create_user_once("prompt-route-user", "prompt-pass")
        self.login_as(user)

        response = self.client.post(
            "/api/prompts",
            json={
                "title": "Route Prompt",
                "command": "/route prompt",
                "category": "Custom",
            },
        )
        self.assertEqual(response.status_code, 200)
        prompt_id = response.get_json()["id"]

        response = self.client.get("/api/prompts")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(prompt["id"] == prompt_id for prompt in response.get_json()["prompts"])
        )

        response = self.client.put(
            f"/api/prompts/{prompt_id}",
            json={
                "title": "Route Prompt Updated",
                "command": "/route prompt updated",
                "category": "Custom",
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.delete(f"/api/prompts/{prompt_id}")
        self.assertEqual(response.status_code, 200)

    @patch("services.telegram_service.requests.post")
    def test_telegram_webhook_rejects_invalid_secret(self, mock_post):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "expected-secret"

        try:
            response = self.client.post(
                "/api/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
                json={
                    "message": {
                        "chat": {"id": 123},
                        "from": {"id": 456},
                        "text": "/help",
                    }
                },
            )

            self.assertEqual(response.status_code, 403)
            mock_post.assert_not_called()
        finally:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)

    @patch("services.telegram_service.requests.post")
    def test_telegram_help_sends_prompt_list(self, mock_post):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "expected-secret"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "456"
        mock_post.return_value.raise_for_status.return_value = None

        try:
            response = self.client.post(
                "/api/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
                json={
                    "message": {
                        "chat": {"id": 123},
                        "from": {"id": 456, "username": "ops_user"},
                        "text": "/help",
                    }
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["status"], "help_sent")
            sent_payload = mock_post.call_args.kwargs["json"]
            self.assertEqual(sent_payload["chat_id"], 123)
            self.assertIn("/diagnose system issue", sent_payload["text"])
        finally:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)

    @patch("services.telegram_service.requests.post")
    def test_telegram_message_calls_langgraph_and_saves_history(self, mock_post):
        user = self.create_user_once("telegram-history-user", "history-pass")
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "expected-secret"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "456"
        os.environ["TELEGRAM_HISTORY_USER_ID"] = str(user["id"])
        mock_post.return_value.raise_for_status.return_value = None

        with patch.object(app_module.langgraph_agent, "run") as mock_run:
            mock_run.return_value = {
                "final_answer": "Fleet is in warning state.",
                "steps": [
                    {
                        "thought": "Inspect fleet status.",
                        "action": "check_system_overview",
                        "output": {"warning_count": 1},
                    }
                ],
                "token_usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
            }

            try:
                response = self.client.post(
                    "/api/telegram/webhook",
                    headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
                    json={
                        "message": {
                            "chat": {"id": 123},
                            "from": {"id": 456, "username": "ops_user"},
                            "text": "/overview system health",
                        }
                    },
                )

                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual(payload["status"], "answered")
                self.assertTrue(payload["history_chat_id"])
                mock_run.assert_called_once_with("/overview system health")

                messages = get_messages(payload["history_chat_id"])
                self.assertEqual(messages[0]["role"], "user")
                self.assertEqual(messages[1]["role"], "assistant")
                self.assertEqual(
                    messages[1]["content"],
                    "Fleet is in warning state.",
                )
                self.assertIn(
                    "check_system_overview",
                    messages[1]["reasoning_steps"],
                )
                sent_payload = mock_post.call_args.kwargs["json"]
                self.assertEqual(sent_payload["text"], "Fleet is in warning state.")
            finally:
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
                os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)
                os.environ.pop("TELEGRAM_HISTORY_USER_ID", None)

    def test_storage_status_api_reports_backend_shape(self):
        user = self.create_user_once("storage-api-user", "storage-pass")
        self.login_as(user)

        response = self.client.get("/api/storage/status")
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(payload["app_data"]["configured_backend"], "sqlite")
        self.assertEqual(payload["app_data"]["active_backend"], "sqlite")
        self.assertTrue(payload["app_data"]["fallback_enabled"])
        self.assertEqual(payload["telemetry"]["source"], "sqlite")

    def test_supabase_url_enables_postgres_when_backend_flag_is_missing(self):
        original_backend = os.environ.get("APP_DB_BACKEND")
        original_supabase_url = os.environ.get("SUPABASE_DB_URL")
        os.environ.pop("APP_DB_BACKEND", None)
        os.environ["SUPABASE_DB_URL"] = "postgresql://example"

        try:
            self.assertTrue(relational_store.using_postgres())
            self.assertEqual(
                relational_store.get_configured_app_db_backend(),
                "supabase",
            )
            self.assertEqual(relational_store.get_app_db_backend(), "supabase")
        finally:
            if original_backend is None:
                os.environ.pop("APP_DB_BACKEND", None)
            else:
                os.environ["APP_DB_BACKEND"] = original_backend

            if original_supabase_url is None:
                os.environ.pop("SUPABASE_DB_URL", None)
            else:
                os.environ["SUPABASE_DB_URL"] = original_supabase_url

    def test_storage_status_records_sqlite_fallback_when_supabase_fails(self):
        original_backend = os.environ.get("APP_DB_BACKEND")
        original_fallback = os.environ.get("APP_DB_FALLBACK_ENABLED")
        os.environ["APP_DB_BACKEND"] = "supabase"
        os.environ["APP_DB_FALLBACK_ENABLED"] = "true"

        try:
            with patch(
                "storage.relational_store.get_postgres_connection",
                side_effect=RuntimeError("simulated supabase outage"),
            ):
                status = relational_store.get_storage_status()
                self.assertEqual(status["app_data"]["active_backend"], "sqlite")
                self.assertFalse(status["app_data"]["healthy"])
                self.assertEqual(
                    status["app_data"]["last_fallback"]["operation"],
                    "health_check",
                )
                self.assertEqual(
                    status["app_data"]["last_fallback"]["fallback_backend"],
                    "sqlite",
                )
        finally:
            if original_backend is None:
                os.environ.pop("APP_DB_BACKEND", None)
            else:
                os.environ["APP_DB_BACKEND"] = original_backend

            if original_fallback is None:
                os.environ.pop("APP_DB_FALLBACK_ENABLED", None)
            else:
                os.environ["APP_DB_FALLBACK_ENABLED"] = original_fallback

    def test_mongodb_telemetry_write_retries_after_transient_failure(self):
        original_enable_mongodb = os.environ.get("ENABLE_MONGODB")
        os.environ["ENABLE_MONGODB"] = "true"
        mongo_store._warned_unavailable = False

        class FakeCollection:
            def __init__(self):
                self.inserted = 0

            def insert_one(self, document):
                self.inserted += 1

        fake_collection = FakeCollection()
        collection_results = [
            RuntimeError("simulated transient mongo outage"),
            fake_collection,
        ]

        def get_collection():
            result = collection_results.pop(0)

            if isinstance(result, Exception):
                raise result

            return result

        telemetry = {
            "device_id": "sensor-001",
            "cpu_usage": 50,
            "memory_usage": 50,
            "heartbeat_delay": 20,
            "status": "healthy",
            "log_message": "normal telemetry transmission",
        }

        try:
            with patch("storage.mongo_store.get_telemetry_collection", get_collection):
                self.assertFalse(mongo_store.insert_telemetry_if_enabled(**telemetry))
                self.assertTrue(mongo_store.insert_telemetry_if_enabled(**telemetry))

            self.assertEqual(fake_collection.inserted, 1)
        finally:
            if original_enable_mongodb is None:
                os.environ.pop("ENABLE_MONGODB", None)
            else:
                os.environ["ENABLE_MONGODB"] = original_enable_mongodb

    def test_supabase_error_raises_when_fallback_disabled(self):
        original_backend = os.environ.get("APP_DB_BACKEND")
        original_fallback = os.environ.get("APP_DB_FALLBACK_ENABLED")
        os.environ["APP_DB_BACKEND"] = "supabase"
        os.environ["APP_DB_FALLBACK_ENABLED"] = "false"

        try:
            with patch(
                "storage.relational_store.get_postgres_connection",
                side_effect=RuntimeError("simulated supabase outage"),
            ):
                with self.assertRaises(RuntimeError):
                    create_chat(1, "Should not fallback")
        finally:
            if original_backend is None:
                os.environ.pop("APP_DB_BACKEND", None)
            else:
                os.environ["APP_DB_BACKEND"] = original_backend

            if original_fallback is None:
                os.environ.pop("APP_DB_FALLBACK_ENABLED", None)
            else:
                os.environ["APP_DB_FALLBACK_ENABLED"] = original_fallback

    def test_storage_status_reports_unavailable_when_fallback_disabled(self):
        original_backend = os.environ.get("APP_DB_BACKEND")
        original_fallback = os.environ.get("APP_DB_FALLBACK_ENABLED")
        os.environ["APP_DB_BACKEND"] = "supabase"
        os.environ["APP_DB_FALLBACK_ENABLED"] = "false"

        try:
            with patch(
                "storage.relational_store.get_postgres_connection",
                side_effect=RuntimeError("simulated supabase outage"),
            ):
                status = relational_store.get_storage_status()
                self.assertEqual(
                    status["app_data"]["active_backend"],
                    "unavailable",
                )
                self.assertFalse(status["app_data"]["fallback_enabled"])
                self.assertFalse(status["app_data"]["healthy"])
        finally:
            if original_backend is None:
                os.environ.pop("APP_DB_BACKEND", None)
            else:
                os.environ["APP_DB_BACKEND"] = original_backend

            if original_fallback is None:
                os.environ.pop("APP_DB_FALLBACK_ENABLED", None)
            else:
                os.environ["APP_DB_FALLBACK_ENABLED"] = original_fallback


def tearDownModule():
    os.chdir(_ORIGINAL_CWD)
    _TEMP_DIR.cleanup()


if __name__ == "__main__":
    unittest.main()
