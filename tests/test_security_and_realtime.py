import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch


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
import storage.postgres_store as postgres_store  # noqa: E402
import storage.relational_store as relational_store  # noqa: E402
import services.telegram_service as telegram_service  # noqa: E402
import services.diagnose_service as diagnose_service  # noqa: E402
import routes.telemetry_routes as telemetry_routes  # noqa: E402
import routes.auth_routes as auth_routes  # noqa: E402
from agents.langgraph_agent import LangGraphAgent  # noqa: E402
from services.chat_service import normalize_token_usage  # noqa: E402
from services.company_data_service import (  # noqa: E402
    enrich_company_metrics,
    extract_display_metrics,
    get_company_agent_context,
    get_metric_value,
    normalize_company_key,
)
from services.company_poc_rule_service import (  # noqa: E402
    POC_RULE_DISCLAIMER,
    evaluate_company_poc_rules,
)
from storage.relational_store import (  # noqa: E402
    add_message,
    create_telegram_link_code,
    create_chat,
    create_user,
    get_telegram_identity,
    get_messages,
    init_db,
    update_user_data_source_policy,
    upsert_telegram_identity,
    verify_user,
)
from services.telegram_link_service import hash_link_code  # noqa: E402


class SecurityAndRealtimeTests(unittest.TestCase):
    def setUp(self):
        relational_store._last_fallback = None
        relational_store._postgres_circuit_open_until = 0.0
        telegram_service._telegram_updates_inflight.clear()
        telegram_service._telegram_updates_processed.clear()
        telemetry_routes._user_data_sources.clear()
        telemetry_routes._mongo_read_rate_limit_log.clear()
        auth_routes._login_rate_limit_log.clear()
        for postgres_url_var in ("SUPABASE_DB_URL", "DATABASE_URL", "POSTGRES_URL"):
            os.environ.pop(postgres_url_var, None)
        for telegram_var in (
            "TELEGRAM_ALLOWED_USER_IDS",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_HISTORY_USER_ID",
        ):
            os.environ.pop(telegram_var, None)
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

    def map_telegram_user(
        self,
        telegram_user_id,
        user,
        allowed_data_sources=None,
        role="operator",
        is_active=True,
    ):
        upsert_telegram_identity(
            telegram_user_id,
            user["id"],
            telegram_username=f"telegram_{telegram_user_id}",
            role=role,
            allowed_data_sources=allowed_data_sources or ["simulator"],
            is_active=is_active,
        )

    def grant_company_data_source(self, user, default_source="company"):
        update_user_data_source_policy(
            user["id"],
            allowed_data_sources=["simulator", "company"],
            default_data_source=default_source,
        )

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

    def test_postgres_connections_apply_query_timeouts(self):
        original_pool = postgres_store._pool
        original_pool_url = postgres_store._pool_url
        fake_pool = MagicMock()
        fake_pool.connection.return_value = object()

        try:
            postgres_store._pool = None
            postgres_store._pool_url = None

            with patch.dict(os.environ, {
                "SUPABASE_DB_URL": "postgresql://example.test/app",
                "POSTGRES_CONNECT_TIMEOUT_SECONDS": "4",
                "POSTGRES_STATEMENT_TIMEOUT_MS": "7000",
                "POSTGRES_LOCK_TIMEOUT_MS": "2000",
            }), patch.object(
                postgres_store,
                "ConnectionPool",
                return_value=fake_pool,
            ) as pool_class:
                postgres_store.get_postgres_connection()

            pool_kwargs = pool_class.call_args.kwargs["kwargs"]
            self.assertEqual(pool_kwargs["connect_timeout"], 4)
            self.assertIn(
                "statement_timeout=7000",
                pool_kwargs["options"],
            )
            self.assertIn("lock_timeout=2000", pool_kwargs["options"])
            fake_pool.connection.assert_called_once_with(timeout=5.0)
        finally:
            postgres_store._pool = original_pool
            postgres_store._pool_url = original_pool_url

    def test_token_usage_normalization_preserves_runtime_metadata(self):
        normalized = normalize_token_usage({
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "runtime_label": "IOA v2 · LangGraph",
            "model_name": "gpt-4o-mini",
        })

        self.assertEqual(
            normalized["runtime_label"],
            "IOA v2 · LangGraph",
        )
        self.assertEqual(normalized["model_name"], "gpt-4o-mini")

    def test_postgres_timeouts_are_applied_after_pool_checkout(self):
        connection = MagicMock()
        connection_context = MagicMock()
        connection_context.__enter__.return_value = connection
        connection_context.__exit__.return_value = False

        with patch.dict(os.environ, {
            "POSTGRES_STATEMENT_TIMEOUT_MS": "4500",
            "POSTGRES_LOCK_TIMEOUT_MS": "2500",
        }):
            with postgres_store.PostgresConnectionContext(
                connection_context
            ) as checked_out_connection:
                self.assertIs(checked_out_connection, connection)

        cursor = connection.cursor.return_value.__enter__.return_value
        query_args = cursor.execute.call_args.args
        self.assertIn("set_config('statement_timeout'", query_args[0])
        self.assertEqual(query_args[1], ("4500ms", "2500ms"))
        connection_context.__exit__.assert_called_once_with(
            None,
            None,
            None,
        )

    def test_postgres_circuit_breaker_uses_sqlite_after_failure(self):
        postgres_calls = []
        sqlite_calls = []

        with patch.object(
            relational_store,
            "using_postgres",
            return_value=True,
        ), patch.dict(os.environ, {
            "APP_DB_FALLBACK_ENABLED": "true",
            "POSTGRES_CIRCUIT_BREAKER_SECONDS": "30",
        }):
            first_result = relational_store._with_fallback(
                "get_messages",
                lambda: (
                    postgres_calls.append("called"),
                    (_ for _ in ()).throw(RuntimeError("query timed out")),
                )[1],
                lambda: sqlite_calls.append("called") or ["fallback"],
            )
            second_result = relational_store._with_fallback(
                "get_messages",
                lambda: postgres_calls.append("called") or ["postgres"],
                lambda: sqlite_calls.append("called") or ["fallback"],
            )

        self.assertEqual(first_result, ["fallback"])
        self.assertEqual(second_result, ["fallback"])
        self.assertEqual(len(postgres_calls), 1)
        self.assertEqual(len(sqlite_calls), 2)

    def test_postgres_pool_timeout_falls_back_without_retry(self):
        postgres_calls = []

        with patch.object(
            relational_store,
            "using_postgres",
            return_value=True,
        ), patch.dict(os.environ, {
            "APP_DB_FALLBACK_ENABLED": "true",
        }):
            result = relational_store._with_fallback(
                "get_messages",
                lambda: (
                    postgres_calls.append("called"),
                    (_ for _ in ()).throw(
                        RuntimeError(
                            "couldn't get a connection after 5.00 sec"
                        )
                    ),
                )[1],
                lambda: ["fallback"],
            )

        self.assertEqual(result, ["fallback"])
        self.assertEqual(len(postgres_calls), 1)

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

    def test_sql_injection_payloads_do_not_bypass_login_or_damage_tables(self):
        user = self.create_user_once("sql-owner", "sql-owner-pass")
        injection = "' OR 1=1; DROP TABLE users; --"

        response = self.client.post(
            "/api/login",
            json={
                "username": injection,
                "password": injection,
            },
        )
        self.assertEqual(response.status_code, 401)

        self.login_as(user)
        response = self.client.post(
            "/api/prompts",
            json={
                "title": injection,
                "command": injection,
                "category": "Security test",
            },
        )
        self.assertEqual(response.status_code, 200)

        self.assertIsNotNone(verify_user("sql-owner", "sql-owner-pass"))
        prompts_response = self.client.get("/api/prompts")
        self.assertEqual(prompts_response.status_code, 200)
        self.assertTrue(any(
            prompt["title"] == injection
            for prompt in prompts_response.get_json()["prompts"]
        ))

    def test_login_rate_limit_blocks_repeated_password_guessing(self):
        self.create_user_once("brute-force-target", "correct-password")

        with patch.dict(os.environ, {
            "LOGIN_RATE_LIMIT_ATTEMPTS": "2",
            "LOGIN_RATE_LIMIT_WINDOW_SECONDS": "60",
        }):
            first = self.client.post(
                "/api/login",
                json={
                    "username": "brute-force-target",
                    "password": "wrong-1",
                },
            )
            second = self.client.post(
                "/api/login",
                json={
                    "username": "brute-force-target",
                    "password": "wrong-2",
                },
            )
            blocked = self.client.post(
                "/api/login",
                json={
                    "username": "brute-force-target",
                    "password": "correct-password",
                },
            )
            other_account = self.client.post(
                "/api/login",
                json={
                    "username": "different-account",
                    "password": "wrong",
                },
            )

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(blocked.status_code, 429)
        self.assertTrue(blocked.headers.get("Retry-After"))
        self.assertEqual(other_account.status_code, 401)

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

    def test_mongo_routes_clamp_read_limits_and_disallow_index_writes(self):
        user = self.create_user_once("mongo-limit-user", "mongo-limit-pass")
        self.login_as(user)

        with patch.object(
            telemetry_routes,
            "get_mongo_telemetry_health_payload",
            return_value={"latest": []},
        ) as health_payload:
            response = self.client.get(
                "/api/mongo/telemetry/health?limit=999999"
            )

        self.assertEqual(response.status_code, 200)
        health_payload.assert_called_once_with(999999)

        with patch(
            "services.telemetry_service.get_telemetry_health",
            return_value={"latest": []},
        ) as mongo_health:
            from services.telemetry_service import (
                get_mongo_telemetry_health_payload,
            )

            get_mongo_telemetry_health_payload(999999)

        mongo_health.assert_called_once_with(limit=100)

        response = self.client.post("/api/mongo/telemetry/indexes")
        self.assertEqual(response.status_code, 405)

    def test_mongo_routes_do_not_expose_database_exception_details(self):
        user = self.create_user_once("mongo-error-user", "mongo-error-pass")
        self.login_as(user)
        secret_error = (
            "mongodb://admin:super-secret@internal-db.example:27017 failed"
        )

        with patch.object(
            telemetry_routes,
            "get_mongo_devices_payload",
            side_effect=RuntimeError(secret_error),
        ):
            response = self.client.get("/api/mongo/devices")

        self.assertEqual(response.status_code, 503)
        body = response.get_data(as_text=True)
        self.assertNotIn("super-secret", body)
        self.assertNotIn("internal-db.example", body)
        self.assertNotIn("details", response.get_json())

    def test_company_fallback_does_not_expose_database_exception_details(self):
        secret_error = (
            "mongodb://admin:company-secret@company-db.internal failed"
        )

        with patch(
            "services.telemetry_service.get_company_device_history",
            side_effect=RuntimeError(secret_error),
        ), patch(
            "services.telemetry_service.get_device_telemetry_history",
            return_value=[],
        ):
            from services.telemetry_service import get_device_history_payload

            payload = get_device_history_payload(
                "sensor-001",
                selected_source="company",
            )

        serialized = json.dumps(payload)
        self.assertNotIn("company-secret", serialized)
        self.assertNotIn("company-db.internal", serialized)
        self.assertEqual(
            payload["reason"],
            "Company MongoDB history read failed.",
        )

    def test_storage_status_does_not_expose_database_exception_details(self):
        secret_error = (
            "postgresql://admin:db-secret@private-db.internal/app failed"
        )

        with patch.object(
            relational_store,
            "using_postgres",
            return_value=True,
        ), patch.object(
            relational_store,
            "get_postgres_connection",
            side_effect=RuntimeError(secret_error),
        ), patch.dict(os.environ, {
            "APP_DB_FALLBACK_ENABLED": "true",
        }):
            payload = relational_store.get_storage_status()

        serialized = json.dumps(payload)
        self.assertNotIn("db-secret", serialized)
        self.assertNotIn("private-db.internal", serialized)
        self.assertEqual(payload["app_data"]["error"], "RuntimeError")
        self.assertEqual(
            payload["app_data"]["last_fallback"]["error"],
            "RuntimeError",
        )

    def test_diagnose_responses_do_not_expose_runtime_exception_details(self):
        user = self.create_user_once("runtime-error-user", "runtime-error-pass")
        self.login_as(user)
        secret_error = (
            "provider failed with api_key=secret-key "
            "at postgresql://admin:db-pass@private-db.internal/app"
        )

        with patch.object(
            app_module.ioa_v2_agent,
            "run",
            side_effect=RuntimeError(secret_error),
        ):
            sync_response = self.client.post(
                "/api/diagnose",
                json={
                    "message": "check system",
                    "mode": "ioa_v2_custom",
                },
            )
            stream_response = self.client.post(
                "/api/diagnose-stream",
                json={
                    "message": "check system",
                    "mode": "ioa_v2_custom",
                },
            )

        sync_body = sync_response.get_data(as_text=True)
        stream_body = stream_response.get_data(as_text=True)

        self.assertEqual(sync_response.status_code, 500)
        self.assertNotIn("secret-key", sync_body)
        self.assertNotIn("db-pass", sync_body)
        self.assertNotIn("private-db.internal", sync_body)
        self.assertNotIn("secret-key", stream_body)
        self.assertNotIn("db-pass", stream_body)
        self.assertNotIn("private-db.internal", stream_body)
        self.assertIn("runtime failed", sync_body)
        self.assertIn("runtime failed", stream_body)

    def test_mongo_read_rate_limit_is_enforced_per_user(self):
        first_user = self.create_user_once(
            "mongo-rate-user",
            "mongo-rate-pass",
        )
        second_user = self.create_user_once(
            "mongo-rate-user-2",
            "mongo-rate-pass-2",
        )

        with patch.dict(os.environ, {
            "MONGO_READ_RATE_LIMIT_REQUESTS": "1",
            "MONGO_READ_RATE_LIMIT_WINDOW_SECONDS": "60",
        }), patch.object(
            telemetry_routes,
            "get_mongo_devices_payload",
            return_value={"source": "mongodb", "devices": []},
        ):
            self.login_as(first_user)
            first_response = self.client.get("/api/mongo/devices")
            limited_response = self.client.get("/api/mongo/devices")

            self.login_as(second_user)
            second_user_response = self.client.get("/api/mongo/devices")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(limited_response.status_code, 429)
        self.assertTrue(limited_response.headers.get("Retry-After"))
        self.assertEqual(second_user_response.status_code, 200)

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
        self.assertEqual(
            devices_payload["alerts"]["telemetry_stream_status"],
            "connected",
        )
        self.assertIsNotNone(
            devices_payload["alerts"]["telemetry_age_seconds"],
        )

        response = self.client.get("/api/telemetry/sensor-001")
        self.assertEqual(response.status_code, 200)
        history_payload = response.get_json()
        self.assertEqual(history_payload["source"], "sqlite")
        self.assertEqual(history_payload["device_id"], "sensor-001")

    def test_data_source_switch_to_company_returns_rules_pending(self):
        user = self.create_user_once("company-source-user", "company-pass")
        self.grant_company_data_source(user)
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

    def test_company_device_history_uses_company_source(self):
        user = self.create_user_once("company-history-user", "history-pass")
        self.grant_company_data_source(user)
        self.login_as(user)
        self.client.post(
            "/api/data-source",
            json={"selected_source": "company"},
        )

        with patch(
            "services.telemetry_service.get_company_device_history",
            return_value={
                "source": "company_mongodb",
                "device_id": "device-1",
                "history": [
                    {
                        "timestamp": 123,
                        "metrics": [
                            {
                                "name": "temperature",
                                "value": 28,
                                "type": "int",
                                "unit": "oC",
                            }
                        ],
                    }
                ],
            },
        ) as company_history:
            response = self.client.get("/api/telemetry/device-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "company_mongodb")
        company_history.assert_called_once_with("device-1")

    def test_company_device_history_falls_back_with_simulator(self):
        user = self.create_user_once(
            "company-history-fallback-user",
            "history-pass",
        )
        self.grant_company_data_source(user)
        self.login_as(user)
        self.client.post(
            "/api/data-source",
            json={"selected_source": "company"},
        )

        with patch(
            "services.telemetry_service.get_company_device_history",
            side_effect=RuntimeError("company DB unavailable"),
        ):
            response = self.client.get("/api/telemetry/sensor-001")

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["selected_source"], "company")
        self.assertEqual(payload["active_source"], "simulator_fallback")
        self.assertEqual(payload["device_id"], "sensor-001")

    def test_company_payload_metrics_are_extracted_for_adaptive_ui(self):
        metrics = extract_display_metrics(
            '{"telemetry":{"temperature":28.5,"humidity":72},"online":true}'
        )

        self.assertEqual(
            metrics,
            [
                {
                    "name": "telemetry.temperature",
                    "value": 28.5,
                    "type": "float",
                },
                {
                    "name": "telemetry.humidity",
                    "value": 72,
                    "type": "int",
                },
                {
                    "name": "online",
                    "value": True,
                    "type": "bool",
                },
            ],
        )

        element_metrics = extract_display_metrics(
            '{"elements":[{"name":"temperature","value":29.2},'
            '{"name":"humidity","value":68}]}'
        )
        self.assertEqual(
            element_metrics,
            [
                {
                    "name": "temperature",
                    "value": 29.2,
                    "type": "float",
                },
                {
                    "name": "humidity",
                    "value": 68,
                    "type": "int",
                },
            ],
        )

    def test_company_agent_context_describes_unified_devices(self):
        records = [
            {
                "record_id": f"device-{index}",
                "device_id": f"device-{index}",
                "device_name": f"Device {index}",
                "status": "connected",
                "status_source": "payload",
                "inventory_source": "devicemgmt.NODE",
                "node_id": f"node-{index}",
                "category": "sensor",
                "model": "model-a",
                "protocol": "mqtt",
                "parent_container": f"cnt-{index}",
                "timestamp": index,
                "tenant_name": "tenant",
                "app_domain_name": "domain",
                "telemetry_record_count": index + 1,
                "rule_count": 1,
                "metrics": [
                    {"name": "temperature", "value": 20 + index}
                ],
            }
            for index in range(7)
        ]

        with patch(
            "services.company_data_service.get_company_operational_payload",
            return_value={
                "source": "company_mongodb",
                "provenance": {
                    "collections": [
                        "devicemgmt.NODE",
                        "datamgmt.CIN",
                    ],
                },
                "summary": {"rule_count": 2},
                "devices": records,
                "rules_status": "available_unmapped",
                "rules_message": "Rule evaluation is pending.",
            },
        ):
            context = get_company_agent_context()

        self.assertEqual(context["record_count"], 7)
        self.assertEqual(
            context["record_type"],
            "unified company devices",
        )
        self.assertEqual(context["distinct_device_count"], 7)
        self.assertEqual(len(context["sample_records"]), 5)
        self.assertNotIn("status", context["sample_records"][0])
        self.assertIn(
            "devicemgmt.NODE",
            context["interpretation_notes"][0],
        )
        self.assertEqual(
            context["classification_status"],
            "provisional_poc_rules_active",
        )

    def test_agent_source_resolver_uses_company_only_when_active(self):
        company_context = {
            "source": "company_mongodb",
            "record_count": 3,
            "sample_records": [{"device_id": "company-device-1"}],
        }

        with patch(
            "services.diagnose_service.get_company_agent_context",
            return_value=company_context,
        ):
            resolved = diagnose_service.resolve_agent_operational_context(
                "company"
            )

        self.assertEqual(resolved["active_source"], "company_mongodb")
        self.assertIs(resolved["operational_context"], company_context)

        with patch(
            "services.diagnose_service.get_company_agent_context",
            return_value={
                "source": "simulator_fallback",
                "reason": "company DB disconnected",
            },
        ):
            fallback = diagnose_service.resolve_agent_operational_context(
                "company"
            )

        self.assertEqual(fallback["active_source"], "simulator_fallback")
        self.assertIsNone(fallback["operational_context"])
        self.assertEqual(
            fallback["fallback_reason"],
            "company DB disconnected",
        )

    def test_n8n_payload_uses_resolved_company_context(self):
        company_context = {
            "source": "company_mongodb",
            "record_count": 1,
            "sample_records": [{"device_id": "company-device-1"}],
        }
        payload = diagnose_service.build_n8n_payload(
            "show fleet status",
            {
                "selected_source": "company",
                "active_source": "company_mongodb",
                "operational_context": company_context,
                "fallback_reason": None,
            },
        )

        self.assertIs(payload["operational_context"], company_context)
        self.assertEqual(payload["active_source"], "company_mongodb")
        self.assertIn(
            "authoritative data source",
            payload["system_prompt"],
        )

    def test_all_sync_agent_modes_receive_resolved_company_source(self):
        user = self.create_user_once("all-company-agents", "company-pass")
        self.login_as(user)
        company_context = {
            "source": "company_mongodb",
            "record_count": 2,
            "sample_records": [{"device_id": "company-device-1"}],
        }
        resolution = {
            "selected_source": "company",
            "active_source": "company_mongodb",
            "operational_context": company_context,
            "fallback_reason": None,
        }

        with (
            patch(
                "routes.diagnose_routes.resolve_agent_operational_context",
                return_value=resolution,
            ),
            patch.object(
                app_module.ioa_v1_agent,
                "run_with_operational_context",
                return_value={"final_answer": "v1 company"},
            ) as ioa_v1_company,
            patch.object(
                app_module.ioa_v2_agent,
                "run_with_operational_context",
                return_value={
                    "final_answer": "v2 company",
                    "steps": [],
                },
            ) as ioa_v2_company,
            patch.object(
                app_module.langchain_agent,
                "run",
                return_value={
                    "final_answer": "langchain company",
                    "steps": [],
                },
            ) as langchain_run,
            patch.object(
                app_module.langgraph_agent,
                "run",
                return_value={
                    "final_answer": "langgraph company",
                    "steps": [],
                },
            ) as langgraph_run,
            patch(
                "routes.diagnose_routes.call_n8n_agent",
                return_value={
                    "final_answer": "n8n company",
                    "steps": [],
                },
            ) as n8n_run,
            patch(
                "routes.diagnose_routes.call_dify_agent",
                return_value={
                    "final_answer": "dify company",
                    "steps": [],
                },
            ) as dify_run,
        ):
            for mode in (
                "ioa_v1_custom",
                "ioa_v2_custom",
                "ioa_v2_langchain",
                "ioa_v2_langgraph",
                "ioa_v2_n8n",
                "ioa_v2_dify",
            ):
                with self.subTest(mode=mode):
                    response = self.client.post(
                        "/api/diagnose",
                        json={
                            "message": "show company fleet",
                            "mode": mode,
                            "data_source": "company",
                        },
                    )
                    self.assertEqual(response.status_code, 200)

        ioa_v1_company.assert_called_once_with(
            "show company fleet",
            company_context,
        )
        ioa_v2_company.assert_called_once_with(
            "show company fleet",
            company_context,
        )
        langchain_run.assert_called_once_with(
            "show company fleet",
            operational_context=company_context,
        )
        langgraph_run.assert_called_once_with(
            "show company fleet",
            data_source="company",
        )
        n8n_run.assert_called_once_with(
            "show company fleet",
            source_resolution=resolution,
        )
        dify_run.assert_called_once_with(
            "show company fleet",
            source_resolution=resolution,
        )

    def test_disconnected_company_source_routes_agents_to_simulator(self):
        user = self.create_user_once("fallback-agents", "fallback-pass")
        self.login_as(user)
        resolution = {
            "selected_source": "company",
            "active_source": "simulator_fallback",
            "operational_context": None,
            "fallback_reason": "company DB disconnected",
        }

        with (
            patch(
                "routes.diagnose_routes.resolve_agent_operational_context",
                return_value=resolution,
            ),
            patch.object(
                app_module.ioa_v2_agent,
                "run",
                return_value={
                    "final_answer": "simulator answer",
                    "steps": [],
                },
            ) as simulator_run,
            patch.object(
                app_module.ioa_v2_agent,
                "run_with_operational_context",
            ) as company_run,
            patch.object(
                app_module.langgraph_agent,
                "run",
                return_value={
                    "final_answer": "simulator graph answer",
                    "steps": [],
                },
            ) as langgraph_run,
        ):
            response = self.client.post(
                "/api/diagnose",
                json={
                    "message": "show fleet",
                    "mode": "ioa_v2_custom",
                    "data_source": "company",
                },
            )
            self.assertEqual(response.status_code, 200)

            response = self.client.post(
                "/api/diagnose",
                json={
                    "message": "show fleet",
                    "mode": "ioa_v2_langgraph",
                    "data_source": "company",
                },
            )
            self.assertEqual(response.status_code, 200)

        simulator_run.assert_called_once_with("show fleet")
        company_run.assert_not_called()
        langgraph_run.assert_called_once_with(
            "show fleet",
            data_source="simulator",
        )

    def test_streaming_custom_agent_uses_active_company_context(self):
        user = self.create_user_once("stream-company-agent", "stream-pass")
        self.login_as(user)
        company_context = {
            "source": "company_mongodb",
            "record_count": 1,
        }
        resolution = {
            "selected_source": "company",
            "active_source": "company_mongodb",
            "operational_context": company_context,
            "fallback_reason": None,
        }

        with (
            patch(
                "routes.diagnose_routes.resolve_agent_operational_context",
                return_value=resolution,
            ),
            patch.object(
                app_module.ioa_v2_agent,
                "run_stream_with_operational_context",
                return_value=iter([{
                    "type": "final",
                    "final_answer": "company stream answer",
                }]),
            ) as company_stream,
            patch.object(
                app_module.ioa_v2_agent,
                "run_stream",
            ) as simulator_stream,
        ):
            response = self.client.post(
                "/api/diagnose-stream",
                json={
                    "message": "show company fleet",
                    "mode": "ioa_v2_custom",
                    "data_source": "company",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "company stream answer",
            response.get_data(as_text=True),
        )
        company_stream.assert_called_once_with(
            "show company fleet",
            company_context,
        )
        simulator_stream.assert_not_called()

    def test_custom_agent_collects_tool_evidence_before_early_final(self):
        agent = app_module.ioa_v2_agent

        with (
            patch.object(agent, "extract_target", return_value="SYSTEM"),
            patch.object(
                agent,
                "choose_next_step",
                side_effect=[
                    "FINAL ANSWER: unsupported early answer",
                    "FINAL ANSWER: grounded answer",
                ],
            ),
            patch.object(
                agent,
                "execute_tool",
                return_value={"total_devices": 10},
            ) as execute_tool,
            patch.object(agent, "save_to_history"),
        ):
            result = agent.run("show fleet health")

        self.assertEqual(result["final_answer"], "grounded answer")
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(
            result["steps"][0]["action"],
            "check_system_overview",
        )
        execute_tool.assert_called_once_with(
            "check_system_overview",
            "SYSTEM",
        )

    def test_custom_agent_stream_emits_forced_tool_trace(self):
        agent = app_module.ioa_v2_agent

        with (
            patch.object(agent, "extract_target", return_value="sensor-001"),
            patch.object(
                agent,
                "choose_next_step",
                side_effect=[
                    "FINAL ANSWER: unsupported early answer",
                    "FINAL ANSWER: grounded answer",
                ],
            ),
            patch.object(
                agent,
                "execute_tool",
                return_value={"device_id": "sensor-001"},
            ),
            patch.object(agent, "save_to_history"),
        ):
            events = list(agent.run_stream("diagnose sensor-001"))

        self.assertEqual(
            [event["type"] for event in events],
            ["thought", "observation", "final"],
        )
        self.assertEqual(
            events[0]["action"],
            "check_device_status",
        )
        self.assertEqual(
            events[1]["observation"]["output"]["device_id"],
            "sensor-001",
        )

    def test_custom_company_agent_collects_focused_tool_evidence(self):
        agent = app_module.ioa_v2_agent
        company_context = {
            "source": "company_mongodb",
            "record_count": 45,
            "distinct_device_count": 45,
            "rules_status": "provisional_poc",
            "summary": {"device_count": 45},
            "provenance": {"collections": ["datamgmt.CIN"]},
        }

        with (
            patch.object(
                agent,
                "choose_company_tool",
                return_value="inspect_company_fleet_summary",
            ),
            patch.object(
                agent,
                "generate_context_answer",
                return_value="grounded company answer",
            ) as generate_answer,
            patch.object(agent, "save_to_history"),
        ):
            result = agent.run_with_operational_context(
                "show company fleet",
                company_context,
            )

        self.assertEqual(result["final_answer"], "grounded company answer")
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(
            [step["action"] for step in result["steps"]],
            [
                "read_company_operational_context",
                "inspect_company_fleet_summary",
            ],
        )
        self.assertEqual(
            result["steps"][1]["output"]["summary"]["device_count"],
            45,
        )
        generate_answer.assert_called_once_with(
            "show company fleet",
            company_context,
            result["steps"],
        )

    def test_custom_company_stream_emits_database_tool_iteration(self):
        agent = app_module.ioa_v2_agent
        company_context = {
            "source": "company_mongodb",
            "record_count": 45,
            "rules_status": "provisional_poc",
            "provenance": {"collections": ["datamgmt.CIN"]},
        }

        with (
            patch.object(
                agent,
                "choose_company_tool",
                return_value="get_company_disconnected_devices",
            ),
            patch(
                "agents.ioa_v2_agent.get_company_disconnected_context",
                return_value={
                    "source": "company_mongodb",
                    "count": 6,
                    "devices": [],
                },
            ) as disconnected_tool,
            patch.object(
                agent,
                "generate_context_answer",
                return_value="six disconnected devices",
            ),
            patch.object(agent, "save_to_history"),
        ):
            events = list(agent.run_stream_with_operational_context(
                "show disconnected company devices",
                company_context,
            ))

        self.assertEqual(
            [event["type"] for event in events],
            [
                "thought",
                "observation",
                "thought",
                "observation",
                "final",
            ],
        )
        self.assertEqual(
            events[2]["action"],
            "get_company_disconnected_devices",
        )
        self.assertEqual(
            events[3]["observation"]["output"]["count"],
            6,
        )
        disconnected_tool.assert_called_once_with()

    def test_company_metric_identity_values_are_read_from_payload(self):
        metrics = extract_display_metrics(
            '{"deviceId":"device-1","deviceName":"Sensor 1",'
            '"status":"connected"}'
        )

        self.assertEqual(
            get_metric_value(metrics, {"deviceId", "device_id"}),
            "device-1",
        )
        self.assertEqual(
            get_metric_value(metrics, {"status"}),
            "connected",
        )

    def test_company_device_keys_and_numeric_metrics_are_normalized(self):
        self.assertEqual(
            normalize_company_key("dvi-S123"),
            "s123",
        )

    def test_company_poc_rules_generate_traceable_alerts(self):
        alerts = evaluate_company_poc_rules([
            {
                "device_id": "device-1",
                "device_name": "Boiler sensor",
                "status": "disconnected",
                "timestamp": 123,
                "inventory_source": "devicemgmt.NODE",
                "telemetry_record_count": 5,
                "metrics": [
                    {
                        "name": "temperature",
                        "value": 72,
                        "type": "int",
                        "unit": "oC",
                    },
                    {
                        "name": "tags[0].rssi",
                        "value": -75,
                        "type": "int",
                        "unit": "",
                    },
                ],
            }
        ])

        self.assertEqual(alerts["rules_status"], "provisional_poc")
        self.assertFalse(alerts["official"])
        self.assertEqual(alerts["critical_count"], 2)
        self.assertEqual(alerts["warning_count"], 1)
        self.assertEqual(alerts["message"], POC_RULE_DISCLAIMER)
        self.assertTrue(all(
            alert["policy"] == "provisional_fallback"
            for alert in alerts["active_alerts"]
        ))
        self.assertTrue(all(
            alert["evidence"].get("value") is not None
            for alert in alerts["active_alerts"]
        ))

    def test_langgraph_routes_company_demo_prompts_to_specific_tools(self):
        agent = LangGraphAgent.__new__(LangGraphAgent)
        cases = [
            (
                "company provisional alerts with evidence",
                "get_company_provisional_alerts",
            ),
            (
                "company telemetry coverage and unmapped records",
                "get_company_telemetry_coverage",
            ),
            (
                "company rule readiness and Grafana gaps",
                "get_company_rule_readiness",
            ),
            (
                "company disconnected devices",
                "get_company_disconnected_devices",
            ),
            (
                "company inventory and node overview",
                "get_company_inventory",
            ),
            (
                "company device SmartAsset_9b47fedc",
                "get_company_device",
            ),
            (
                "company fleet snapshot",
                "get_company_fleet_summary",
            ),
        ]

        for prompt, expected_tool in cases:
            result = agent.select_tool_node({
                "user_input": prompt,
                "data_source": "company",
                "steps": [],
            })
            self.assertEqual(result["selected_tool"], expected_tool)
        self.assertEqual(
            normalize_company_key("S123"),
            "s123",
        )
        self.assertEqual(
            enrich_company_metrics(
                [
                    {"name": "deviceId", "value": "S123", "type": "str"},
                    {"name": "temp", "value": "28.5", "type": "str"},
                ],
                {"temp": "oC"},
            ),
            [
                {
                    "name": "temp",
                    "value": 28.5,
                    "type": "float",
                    "unit": "oC",
                }
            ],
        )

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

    def test_prompt_routes_reject_cross_user_update_and_delete(self):
        owner = self.create_user_once("prompt-owner", "prompt-owner-pass")
        attacker = self.create_user_once(
            "prompt-attacker",
            "prompt-attacker-pass",
        )
        self.login_as(owner)
        create_response = self.client.post(
            "/api/prompts",
            json={
                "title": "Owner only",
                "command": "/owner-only",
                "category": "Private",
            },
        )
        prompt_id = create_response.get_json()["id"]

        self.login_as(attacker)
        update_response = self.client.put(
            f"/api/prompts/{prompt_id}",
            json={
                "title": "Hijacked",
                "command": "/hijacked",
                "category": "Attack",
            },
        )
        delete_response = self.client.delete(f"/api/prompts/{prompt_id}")

        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)

        self.login_as(owner)
        prompts = self.client.get("/api/prompts").get_json()["prompts"]
        owner_prompt = next(
            prompt for prompt in prompts if prompt["id"] == prompt_id
        )
        self.assertEqual(owner_prompt["title"], "Owner only")
    @patch("services.telegram_service.requests.post")
    def test_telegram_webhook_rejects_invalid_secret(self, mock_post):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "expected-secret"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "456"

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
            os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)

    @patch("services.telegram_service.requests.post")
    def test_telegram_help_sends_prompt_list(self, mock_post):
        user = self.create_user_once("telegram-help-user", "help-pass")
        self.map_telegram_user(456, user)
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
            self.assertEqual(response.get_json()["status"], "accepted")
            deadline = time.monotonic() + 1

            while not mock_post.called and time.monotonic() < deadline:
                time.sleep(0.01)

            self.assertTrue(mock_post.called)
            sent_payload = mock_post.call_args.kwargs["json"]
            self.assertEqual(sent_payload["chat_id"], 123)
            self.assertIn("/diagnose gateway-001", sent_payload["text"])
        finally:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)

    @patch("services.telegram_service.requests.post")
    def test_telegram_unmapped_user_is_denied_before_agent_runs(self, mock_post):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        mock_post.return_value.raise_for_status.return_value = None

        with patch.object(
            app_module.langgraph_agent,
            "run_stream",
        ) as mock_run_stream:
            try:
                payload = telegram_service.process_telegram_update(
                    {
                        "message": {
                            "chat": {"id": 123},
                            "from": {"id": 999, "username": "unknown_user"},
                            "text": "/overview",
                        },
                    },
                    app_module.langgraph_agent,
                )

                self.assertEqual(payload["status"], "forbidden")
                self.assertEqual(
                    payload["reason"],
                    "telegram_identity_not_mapped",
                )
                mock_run_stream.assert_not_called()
                sent_payload = mock_post.call_args.kwargs["json"]
                self.assertEqual(sent_payload["chat_id"], 123)
                self.assertIn("not allowed", sent_payload["text"])
            finally:
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    def test_telegram_link_code_api_requires_login(self):
        response = self.client.post("/api/profile/telegram-link-code")

        self.assertEqual(response.status_code, 401)

    def test_telegram_identity_writes_do_not_fallback_to_sqlite(self):
        os.environ["APP_DB_BACKEND"] = "supabase"
        os.environ["SUPABASE_DB_URL"] = "postgresql://example"

        try:
            with patch(
                "storage.relational_store.get_postgres_connection",
                side_effect=RuntimeError("missing telegram migration"),
            ):
                with self.assertRaises(RuntimeError):
                    relational_store.create_telegram_link_code(
                        "hash",
                        1,
                        "2099-01-01T00:00:00+00:00",
                    )
                with self.assertRaises(RuntimeError):
                    relational_store.update_user_data_source_policy(
                        1,
                        allowed_data_sources=["simulator", "company"],
                        default_data_source="company",
                    )

            self.assertIsNone(
                relational_store.sqlite_store.get_telegram_link_code("hash")
            )
        finally:
            os.environ["APP_DB_BACKEND"] = "sqlite"
            os.environ.pop("SUPABASE_DB_URL", None)

    def test_logged_in_user_can_create_telegram_link_code(self):
        user = self.create_user_once("telegram-link-owner", "link-pass")
        self.login_as(user)

        response = self.client.post("/api/profile/telegram-link-code")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertRegex(payload["code"], r"^[A-Z2-9]{8}$")
        self.assertEqual(payload["ttl_minutes"], 15)
        self.assertIn("expires_at", payload)

    @patch("services.telegram_service.requests.post")
    def test_telegram_link_command_maps_identity_without_agent(self, mock_post):
        user = self.create_user_once("telegram-link-user", "link-pass")
        self.login_as(user)
        code = self.client.post(
            "/api/profile/telegram-link-code"
        ).get_json()["code"]
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        mock_post.return_value.raise_for_status.return_value = None

        with patch.object(
            app_module.langgraph_agent,
            "run_stream",
        ) as mock_run_stream:
            payload = telegram_service.process_telegram_update(
                {
                    "message": {
                        "chat": {"id": 123},
                        "from": {"id": 8806645598, "username": "tg_user"},
                        "text": f"/link {code}",
                    },
                },
                app_module.langgraph_agent,
            )

        self.assertEqual(payload["status"], "linked")
        identity = get_telegram_identity(8806645598)
        self.assertEqual(identity["user_id"], user["id"])
        self.assertEqual(identity["telegram_username"], "tg_user")
        self.assertEqual(identity["role"], "viewer")
        self.assertEqual(identity["allowed_data_sources"], ["simulator"])
        mock_run_stream.assert_not_called()
        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertIn("linked", sent_payload["text"])

    @patch("services.telegram_service.requests.post")
    def test_telegram_link_code_cannot_be_reused(self, mock_post):
        first_user = self.create_user_once("telegram-link-first", "link-pass")
        second_user = self.create_user_once("telegram-link-second", "link-pass")
        self.login_as(first_user)
        code = self.client.post(
            "/api/profile/telegram-link-code"
        ).get_json()["code"]
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        mock_post.return_value.raise_for_status.return_value = None

        first_payload = telegram_service.process_telegram_update(
            {
                "message": {
                    "chat": {"id": 123},
                    "from": {"id": 111, "username": "first"},
                    "text": f"/link {code}",
                },
            },
            app_module.langgraph_agent,
        )
        self.login_as(second_user)
        second_payload = telegram_service.process_telegram_update(
            {
                "message": {
                    "chat": {"id": 124},
                    "from": {"id": 222, "username": "second"},
                    "text": f"/link {code}",
                },
            },
            app_module.langgraph_agent,
        )

        self.assertEqual(first_payload["status"], "linked")
        self.assertEqual(second_payload["status"], "link_failed")
        self.assertEqual(second_payload["reason"], "code_already_used")
        self.assertIsNone(get_telegram_identity(222))

    @patch("services.telegram_service.requests.post")
    def test_telegram_expired_link_code_is_rejected(self, mock_post):
        user = self.create_user_once("telegram-expired-link", "link-pass")
        code = "ABCDEFGH"
        create_telegram_link_code(
            hash_link_code(code),
            user["id"],
            "2000-01-01T00:00:00+00:00",
        )
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        mock_post.return_value.raise_for_status.return_value = None

        payload = telegram_service.process_telegram_update(
            {
                "message": {
                    "chat": {"id": 123},
                    "from": {"id": 333, "username": "expired"},
                    "text": f"/link {code}",
                },
            },
            app_module.langgraph_agent,
        )

        self.assertEqual(payload["status"], "link_failed")
        self.assertEqual(payload["reason"], "code_expired")
        self.assertIsNone(get_telegram_identity(333))

    @patch("services.telegram_service.requests.post")
    def test_telegram_link_requires_sender_id(self, mock_post):
        user = self.create_user_once("telegram-missing-id-link", "link-pass")
        self.login_as(user)
        code = self.client.post(
            "/api/profile/telegram-link-code"
        ).get_json()["code"]
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        mock_post.return_value.raise_for_status.return_value = None

        payload = telegram_service.process_telegram_update(
            {
                "message": {
                    "chat": {"id": 123},
                    "from": {"username": "missing_id"},
                    "text": f"/link {code}",
                },
            },
            app_module.langgraph_agent,
        )

        self.assertEqual(payload["status"], "link_failed")
        self.assertEqual(payload["reason"], "missing_telegram_user_id")
        self.assertIsNone(get_telegram_identity("None"))

    @patch("services.telegram_service.requests.post")
    def test_telegram_inactive_identity_is_denied(self, mock_post):
        user = self.create_user_once("telegram-inactive-user", "inactive-pass")
        self.map_telegram_user(456, user, is_active=False)
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        mock_post.return_value.raise_for_status.return_value = None

        with patch.object(
            app_module.langgraph_agent,
            "run_stream",
        ) as mock_run_stream:
            try:
                payload = telegram_service.process_telegram_update(
                    {
                        "message": {
                            "chat": {"id": 123},
                            "from": {"id": 456, "username": "inactive_user"},
                            "text": "/overview",
                        },
                    },
                    app_module.langgraph_agent,
                )

                self.assertEqual(payload["status"], "forbidden")
                self.assertEqual(payload["reason"], "telegram_identity_inactive")
                mock_run_stream.assert_not_called()
            finally:
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    @patch("services.telegram_service.requests.post")
    def test_telegram_allowlist_still_blocks_mapped_user(self, mock_post):
        user = self.create_user_once("telegram-allowlist-user", "allow-pass")
        self.map_telegram_user(456, user)
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "789"
        mock_post.return_value.raise_for_status.return_value = None

        with patch.object(
            app_module.langgraph_agent,
            "run_stream",
        ) as mock_run_stream:
            try:
                payload = telegram_service.process_telegram_update(
                    {
                        "message": {
                            "chat": {"id": 123},
                            "from": {"id": 456, "username": "ops_user"},
                            "text": "/overview",
                        },
                    },
                    app_module.langgraph_agent,
                )

                self.assertEqual(payload["status"], "forbidden")
                self.assertEqual(
                    payload["reason"],
                    "telegram_user_not_allowlisted",
                )
                mock_run_stream.assert_not_called()
            finally:
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)

    @patch("services.telegram_service.requests.post")
    def test_telegram_company_source_requires_identity_scope(self, mock_post):
        user = self.create_user_once("telegram-scope-user", "scope-pass")
        self.grant_company_data_source(user)
        self.map_telegram_user(456, user, allowed_data_sources=["simulator"])
        telemetry_routes.remember_user_data_source(user["id"], "company")
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        mock_post.return_value.raise_for_status.return_value = None

        with patch.object(
            app_module.langgraph_agent,
            "run_stream",
        ) as mock_run_stream:
            try:
                payload = telegram_service.process_telegram_update(
                    {
                        "message": {
                            "chat": {"id": 123},
                            "from": {"id": 456, "username": "ops_user"},
                            "text": "/companyfleet",
                        },
                    },
                    app_module.langgraph_agent,
                    get_user_data_source=(
                        app_module.get_user_selected_data_source
                    ),
                )

                self.assertEqual(payload["status"], "forbidden")
                self.assertEqual(payload["reason"], "data_source_not_allowed")
                self.assertEqual(payload["data_source"], "company")
                mock_run_stream.assert_not_called()
                sent_payload = mock_post.call_args.kwargs["json"]
                self.assertIn("data source", sent_payload["text"])
            finally:
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    @patch("services.telegram_service.requests.post")
    def test_telegram_message_calls_langgraph_and_saves_history(self, mock_post):
        user = self.create_user_once("telegram-history-user", "history-pass")
        self.grant_company_data_source(user)
        self.map_telegram_user(
            456,
            user,
            allowed_data_sources=["simulator", "company"],
        )
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "expected-secret"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "456"
        mock_post.return_value.raise_for_status.return_value = None
        self.login_as(user)
        socket_client = app_module.socketio.test_client(
            app_module.app,
            flask_test_client=self.client,
        )
        telemetry_routes.remember_user_data_source(user["id"], "company")

        stream_events = [
            {
                "type": "thought",
                "iteration": 1,
                "thought": "Inspect fleet status.",
                "action": "check_system_overview",
                "workflow": {"framework": "LangGraph"},
            },
            {
                "type": "observation",
                "iteration": 1,
                "observation": {"output": {"warning_count": 1}},
            },
            {
                "type": "final",
                "final_answer": "Fleet is in warning state.",
                "token_usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
            },
        ]

        with patch.object(
            app_module.langgraph_agent,
            "run_stream",
            return_value=iter(stream_events),
        ) as mock_run_stream:
            try:
                payload = telegram_service.process_telegram_update(
                    {
                        "message": {
                            "chat": {"id": 123},
                            "from": {"id": 456, "username": "ops_user"},
                            "text": "/overview system health",
                        },
                    },
                    app_module.langgraph_agent,
                    emit_user_event=lambda user_id, event, data: (
                        app_module.socketio.emit(
                            event,
                            data,
                            to=f"user:{user_id}",
                        )
                    ),
                    get_user_data_source=(
                        app_module.get_user_selected_data_source
                    ),
                )

                self.assertEqual(payload["status"], "answered")
                self.assertTrue(payload["history_chat_id"])
                mock_run_stream.assert_called_once_with(
                    "overview system health",
                    data_source="company",
                )

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
                saved_token_usage = json.loads(
                    messages[1]["token_usage"]
                )
                self.assertEqual(
                    saved_token_usage["runtime_label"],
                    "IOA v2 · LangGraph",
                )
                socket_events = socket_client.get_received()
                event_names = [event["name"] for event in socket_events]
                self.assertEqual(event_names[0], "telegram_chat_started")
                self.assertIn("telegram_reasoning_event", event_names)
                self.assertEqual(event_names[-1], "telegram_chat_completed")
                self.assertEqual(
                    socket_events[0]["args"][0]["chat_id"],
                    payload["history_chat_id"],
                )
                sent_payload = mock_post.call_args.kwargs["json"]
                self.assertEqual(sent_payload["text"], "Fleet is in warning state.")
            finally:
                socket_client.disconnect()
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
                os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)

    def test_telegram_commands_map_to_agent_prompts(self):
        self.assertEqual(
            telegram_service.normalize_telegram_prompt("/overview"),
            ("overview system health", None),
        )
        self.assertEqual(
            telegram_service.normalize_telegram_prompt(
                "/diagnose gateway-001"
            ),
            ("diagnose gateway-001", None),
        )
        self.assertEqual(
            telegram_service.normalize_telegram_prompt(
                "/alarms@iot_ops_agent_bot"
            ),
            ("show devices with alarms", None),
        )

    def test_assistant_markdown_is_formatted_as_conversational_text(self):
        formatted = telegram_service.format_conversational_text(
            "### Operational Diagnosis\n\n"
            "#### 1. Summary\n"
            "**gateway-001** needs attention.\n\n"
            "- CPU is `92%`\n"
            "- Check [Grafana](https://grafana.example.com)"
        )

        self.assertNotIn("#", formatted)
        self.assertNotIn("**", formatted)
        self.assertNotIn("`", formatted)
        self.assertIn("1. Summary", formatted)
        self.assertIn("• CPU is 92%", formatted)

    def test_telegram_command_payload_contains_supported_commands(self):
        payload = telegram_service.build_set_commands_payload()
        commands = json.loads(payload["commands"])
        command_names = {item["command"] for item in commands}

        self.assertEqual(
            command_names,
            {
                "overview",
                "unhealthy",
                "alarms",
                "diagnose",
                "heartbeat",
                "companyfleet",
                "coverage",
                "pocalerts",
                "disconnected",
                "ruleready",
                "link",
                "help",
            },
        )

    @patch("services.telegram_service.requests.post")
    def test_telegram_duplicate_update_is_answered_once(self, mock_post):
        user = self.create_user_once("telegram-duplicate-user", "duplicate-pass")
        self.map_telegram_user(456, user)
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "expected-secret"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "456"
        mock_post.return_value.raise_for_status.return_value = None
        update = {
            "update_id": 851724187,
            "message": {
                "chat": {"id": 123},
                "from": {"id": 456, "username": "ops_user"},
                "text": "/overview system health",
            },
        }

        stream_events = [{
            "type": "final",
            "final_answer": "Fleet is stable.",
            "token_usage": None,
        }]

        with patch.object(
            app_module.langgraph_agent,
            "run_stream",
            return_value=iter(stream_events),
        ) as mock_run_stream:
            try:
                first_response = telegram_service.process_telegram_update(
                    update,
                    app_module.langgraph_agent,
                )
                duplicate_response = telegram_service.process_telegram_update(
                    update,
                    app_module.langgraph_agent,
                )

                self.assertEqual(first_response["status"], "answered")
                self.assertEqual(
                    duplicate_response["status"],
                    "duplicate",
                )
                mock_run_stream.assert_called_once_with(
                    "overview system health",
                    data_source="simulator",
                )
                self.assertEqual(mock_post.call_count, 1)
            finally:
                os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
                os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)

    def test_telegram_webhook_returns_before_background_work_finishes(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-telegram-token"
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "expected-secret"
        processing_started = threading.Event()
        release_processing = threading.Event()

        def blocked_processing(*args, **kwargs):
            processing_started.set()
            release_processing.wait(timeout=1)

        try:
            with patch(
                "services.telegram_service.process_telegram_update",
                side_effect=blocked_processing,
            ):
                started_at = time.monotonic()
                response = self.client.post(
                    "/api/telegram/webhook",
                    headers={
                        "X-Telegram-Bot-Api-Secret-Token": "expected-secret"
                    },
                    json={"update_id": 123},
                )
                elapsed = time.monotonic() - started_at
                self.assertTrue(processing_started.wait(timeout=0.2))

                health_started_at = time.monotonic()
                health_response = self.client.get(
                    "/api/telegram/webhook-info"
                )
                health_elapsed = time.monotonic() - health_started_at

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["status"], "accepted")
            self.assertLess(elapsed, 0.2)
            self.assertEqual(health_response.status_code, 200)
            self.assertLess(health_elapsed, 0.2)
        finally:
            release_processing.set()
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)

    def test_telegram_background_failure_notifies_ui(self):
        user = self.create_user_once("telegram-failure-user", "failure-pass")
        self.map_telegram_user(456, user)
        emitted_events = []

        with patch(
            "services.telegram_service.process_telegram_update",
            side_effect=RuntimeError("simulated agent failure"),
        ):
            worker = (
                telegram_service.process_telegram_update_in_background(
                    {
                        "update_id": 999,
                        "message": {
                            "chat": {"id": 123},
                            "from": {"id": 456, "username": "ops_user"},
                            "text": "/overview",
                        },
                    },
                    app_module.langgraph_agent,
                    emit_user_event=lambda user_id, event, payload: (
                        emitted_events.append(
                            (user_id, event, payload)
                        )
                    ),
                )
            )
            worker.join(timeout=1)

        self.assertFalse(worker.is_alive())
        self.assertEqual(
            emitted_events,
            [(
                user["id"],
                "telegram_chat_failed",
                {"error": "Telegram request failed."},
            )],
        )

    def test_data_source_selection_is_remembered_for_telegram_user(self):
        user = self.create_user_once("source-user", "source-pass")
        self.grant_company_data_source(user)
        self.login_as(user)

        response = self.client.post(
            "/api/data-source",
            json={"selected_source": "company"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            app_module.get_user_selected_data_source(user["id"]),
            "company",
        )

    def test_unapproved_user_cannot_select_company_data_source(self):
        user = self.create_user_once("source-denied-user", "source-pass")
        self.login_as(user)

        response = self.client.post(
            "/api/data-source",
            json={"selected_source": "company"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.get_json()
        self.assertEqual(payload["selected_source"], "simulator")
        self.assertEqual(payload["allowed_data_sources"], ["simulator"])
        self.assertEqual(
            app_module.get_user_selected_data_source(user["id"]),
            "simulator",
        )

    def test_new_user_data_source_defaults_to_simulator(self):
        user = self.create_user_once("source-default-user", "source-pass")

        self.assertEqual(
            app_module.get_user_selected_data_source(user["id"]),
            "simulator",
        )

    def test_company_grant_can_default_user_to_company(self):
        user = self.create_user_once("source-company-default", "source-pass")
        self.grant_company_data_source(user)

        self.assertEqual(
            app_module.get_user_selected_data_source(user["id"]),
            "company",
        )

    def test_storage_status_api_reports_backend_shape(self):
        user = self.create_user_once("storage-api-user", "storage-pass")
        self.login_as(user)

        response = self.client.get("/api/storage/status")
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(payload["app_data"]["configured_backend"], "sqlite")
        self.assertEqual(payload["app_data"]["active_backend"], "sqlite")
        self.assertFalse(payload["app_data"]["fallback_enabled"])
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
