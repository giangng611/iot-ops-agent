import os
import unittest
from unittest.mock import MagicMock, patch

from agents.ioa_v3_agent import IOAV3LangGraphN8nAgent
from services.company_data_service import collect_onem2m_identifier_candidates
from services.company_data_service import is_configured_threshold_metric
from services.grafana_tool_registry import (
    build_grafana_workflow_policy,
    get_grafana_tool_by_name,
    get_kpi_rules_for_tool,
)
from services.n8n_gateway_service import (
    DEFAULT_N8N_V3_WEBHOOK_URL,
    build_n8n_v3_payload,
    get_n8n_v3_webhook_url,
)


class IOAV3WorkflowTests(unittest.TestCase):
    def test_grafana_registry_exposes_allowlisted_tools(self):
        tool = get_grafana_tool_by_name("grafana_queue_backlog")
        policy = build_grafana_workflow_policy()

        self.assertEqual(tool["path"], "/grafana/queue-backlog")
        self.assertIn("namespace", tool["allowed_params"])
        self.assertIn("unapproved_grafana_endpoint", policy["forbidden_capabilities"])
        self.assertTrue(any(
            item["tool"] == "grafana_queue_backlog"
            for item in policy["allowed_workflows"]
        ))
        self.assertTrue(any(
            item["tool"] == "grafana_emqx_connection_trend"
            and item["path"] == "/grafana/emqx/connection-trend"
            for item in policy["allowed_workflows"]
        ))

    def test_kpi_rules_are_mapped_to_grafana_tools(self):
        original_flag = os.environ.get("IOA_V3_ENABLE_KPI_RULES")
        os.environ["IOA_V3_ENABLE_KPI_RULES"] = "true"

        try:
            rules = get_kpi_rules_for_tool("grafana_queue_backlog")

            self.assertTrue(rules)
            self.assertEqual(rules[0]["kpi"], "Queue Backlog")
            self.assertEqual(rules[0]["priority"], "Core")
            self.assertEqual(rules[0]["implementation_status"], "dashboarded")

            http_rules = get_kpi_rules_for_tool("grafana_http_health")
            self.assertEqual(
                {rule["kpi"] for rule in http_rules},
                {"API Success Rate", "API Latency P95", "HTTP 5xx Rate"},
            )
        finally:
            if original_flag is None:
                os.environ.pop("IOA_V3_ENABLE_KPI_RULES", None)
            else:
                os.environ["IOA_V3_ENABLE_KPI_RULES"] = original_flag

    def test_kpi_rules_are_enabled_by_default(self):
        original_flag = os.environ.pop("IOA_V3_ENABLE_KPI_RULES", None)

        try:
            self.assertTrue(get_kpi_rules_for_tool("grafana_queue_backlog"))
        finally:
            if original_flag is not None:
                os.environ["IOA_V3_ENABLE_KPI_RULES"] = original_flag

    def test_kpi_rules_can_be_disabled_by_env(self):
        original_flag = os.environ.get("IOA_V3_ENABLE_KPI_RULES")
        os.environ["IOA_V3_ENABLE_KPI_RULES"] = "false"

        try:
            self.assertEqual(get_kpi_rules_for_tool("grafana_queue_backlog"), [])
        finally:
            if original_flag is None:
                os.environ.pop("IOA_V3_ENABLE_KPI_RULES", None)
            else:
                os.environ["IOA_V3_ENABLE_KPI_RULES"] = original_flag

    def test_n8n_v3_payload_filters_unapproved_params(self):
        payload = build_n8n_v3_payload(
            user_input="show http health",
            selected_tool="grafana_http_health",
            params={
                "project": "iot-platform",
                "window": "10m",
                "url": "http://evil.example",
            },
            source_resolution={
                "selected_source": "company",
                "active_source": "company_mongodb",
            },
            user_id=7,
        )

        self.assertEqual(payload["workflow"]["path"], "/grafana/http-health")
        self.assertEqual(
            payload["workflow"]["params"],
            {"project": "iot-platform", "window": "10m"},
        )
        self.assertNotIn("url", payload["workflow"]["params"])
        self.assertEqual(payload["user_id"], 7)
        self.assertEqual(
            payload["grafana_client"]["base_url"],
            "http://127.0.0.1:5050",
        )

    def test_v3_webhook_defaults_to_local_grafana_gateway(self):
        original_v3 = os.environ.pop("N8N_V3_WEBHOOK_URL", None)
        original_grafana = os.environ.pop("N8N_GRAFANA_WEBHOOK_URL", None)
        original_legacy = os.environ.get("N8N_WEBHOOK_URL")
        os.environ["N8N_WEBHOOK_URL"] = "http://localhost:5678/webhook/iot-ops-eval"

        try:
            self.assertEqual(
                get_n8n_v3_webhook_url(),
                DEFAULT_N8N_V3_WEBHOOK_URL,
            )
        finally:
            if original_v3 is not None:
                os.environ["N8N_V3_WEBHOOK_URL"] = original_v3
            if original_grafana is not None:
                os.environ["N8N_GRAFANA_WEBHOOK_URL"] = original_grafana
            if original_legacy is None:
                os.environ.pop("N8N_WEBHOOK_URL", None)
            else:
                os.environ["N8N_WEBHOOK_URL"] = original_legacy

    def test_v3_webhook_rewrites_stale_local_task_broker_port(self):
        original_v3 = os.environ.get("N8N_V3_WEBHOOK_URL")
        original_grafana = os.environ.pop("N8N_GRAFANA_WEBHOOK_URL", None)
        os.environ["N8N_V3_WEBHOOK_URL"] = (
            "http://localhost:5679/webhook/grafana-ops-gateway"
        )

        try:
            self.assertEqual(
                get_n8n_v3_webhook_url(),
                DEFAULT_N8N_V3_WEBHOOK_URL,
            )
        finally:
            if original_v3 is None:
                os.environ.pop("N8N_V3_WEBHOOK_URL", None)
            else:
                os.environ["N8N_V3_WEBHOOK_URL"] = original_v3
            if original_grafana is not None:
                os.environ["N8N_GRAFANA_WEBHOOK_URL"] = original_grafana

    def test_ioa_v3_selects_grafana_tool_from_prompt(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, reason = agent.classify_grafana_tool(
            "check redis health"
        )

        self.assertEqual(tool, "grafana_redis_health")
        self.assertEqual(params, {})
        self.assertEqual(reason, "redis_keywords")

    def test_ioa_v3_routes_trend_prompts_to_typed_grafana_adapters(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        cases = [
            (
                "Check whether RabbitMQ queue messages are increasing linearly",
                "grafana_queue_trend",
            ),
            (
                "Check whether EMQX messages dropped increased",
                "grafana_emqx_dropped_trend",
            ),
            (
                "Check EMQX client connected and disconnected rates",
                "grafana_emqx_connection_trend",
            ),
            (
                "Check Kubernetes resource health in namespace one-iot: pod CPU and memory",
                "grafana_k8s_resources",
            ),
        ]

        for prompt, expected_tool in cases:
            with self.subTest(prompt=prompt):
                tool, _, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)

    def test_ioa_v3_routes_disconnected_devices_to_company_db_tool(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, reason = agent.classify_tool(
            "list disconnected devices from company db"
        )

        self.assertEqual(tool, "get_company_disconnected_devices")
        self.assertEqual(params, {})
        self.assertEqual(reason, "company_disconnected_device_keywords")

    def test_ioa_v3_routes_company_temperature_alerts_to_company_db_tool(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, reason = agent.classify_tool(
            "/company temperature alerts and measured values"
        )

        self.assertEqual(tool, "get_company_provisional_alerts")
        self.assertEqual(params, {})
        self.assertEqual(reason, "company_alert_or_measured_value_keywords")

    def test_ioa_v3_classifies_natural_company_device_prompts(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        cases = [
            (
                "which sensors have high temperature measured values?",
                "get_company_provisional_alerts",
            ),
            (
                "show telemetry coverage and unmapped company payloads",
                "get_company_telemetry_coverage",
            ),
            (
                "are the official company rules ready for grafana integration?",
                "get_company_rule_readiness",
            ),
            (
                "give me a company fleet snapshot",
                "get_company_fleet_summary",
            ),
            (
                "list company inventory devices",
                "get_company_inventory",
            ),
        ]

        for prompt, expected_tool in cases:
            with self.subTest(prompt=prompt):
                tool, _, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)

    def test_ioa_v3_extracts_company_threshold_scan_prompt(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, reason = agent.classify_tool(
            "find devices with temperature above 70"
        )

        self.assertEqual(tool, "scan_company_threshold")
        self.assertEqual(params, {"threshold": 70.0})
        self.assertEqual(reason, "company_threshold_keywords")

    def test_ioa_v3_routes_onem2m_prompts_to_company_db_tools(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        cases = [
            (
                "Debug why device S123 did not receive a command. Check IDENTITY, AE, cnt_command, subscription, URI mapper, latest command CIN.",
                "get_company_onem2m_command_flow",
                {"device_id": "S123"},
            ),
            (
                "Debug why telemetry from device S123 did not reach the backend. Check cnt_telemetry, latest telemetry CIN, backend subscription.",
                "get_company_onem2m_telemetry_flow",
                {"device_id": "S123"},
            ),
            (
                "Check whether device <device_id> is on the platform and whether required OneM2M resources exist: IDENTITY, AE, CNT, CIN, SUBSCRIPTION, and URI_MAPPER.",
                "get_company_onem2m_device_resources",
                {},
            ),
        ]

        for prompt, expected_tool, expected_params in cases:
            with self.subTest(prompt=prompt):
                tool, params, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)
                self.assertEqual(params, expected_params)

    def test_ioa_v3_runbook_override_keeps_command_flow_primary(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        workflows = [
            {
                "tool": "get_company_onem2m_device_resources",
                "params": {"device_id": "S123"},
                "reason": "semantic_resource_check",
                "confidence": 0.8,
                "planner": "semantic_llm",
                "tool_family": "company_db",
            },
            {
                "tool": "grafana_logs",
                "params": {},
                "reason": "logs",
                "confidence": 0.7,
                "planner": "semantic_llm",
                "tool_family": "grafana_n8n",
            },
        ]

        planned = agent.ensure_runbook_required_workflows(
            workflows,
            (
                "Debug why device S123 did not receive a command. Check "
                "adapter logs, core logs, IDENTITY, AE, cnt_command, "
                "subscription, URI mapper, latest command CIN."
            ),
        )

        self.assertEqual(planned[0]["tool"], "get_company_onem2m_command_flow")
        self.assertEqual(planned[0]["params"]["device_id"], "S123")
        self.assertNotIn(
            "get_company_onem2m_device_resources",
            [workflow["tool"] for workflow in planned],
        )

    def test_ioa_v3_replaces_weak_semantic_device_id(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        params = agent.enrich_workflow_params(
            "get_company_onem2m_device_resources",
            {"device_id": "as"},
            (
                "Check whether device "
                "Seeaf28d9-2fc3-4a0d-be53-1212037ff95e is registered"
            ),
        )

        self.assertEqual(
            params["device_id"],
            "Seeaf28d9-2fc3-4a0d-be53-1212037ff95e",
        )

    def test_ioa_v3_ignores_instruction_words_as_identifiers(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        identifiers = agent.extract_onem2m_identifiers(
            (
                "Check whether device "
                "Seeaf28d9-2fc3-4a0d-be53-1212037ff95e is registered. "
                "Treat the device ID as the only required operator input. "
                "Derive AE ID and request/correlation IDs from MongoDB."
            )
        )

        self.assertEqual(
            identifiers["device_id"],
            "Seeaf28d9-2fc3-4a0d-be53-1212037ff95e",
        )
        self.assertNotIn("ae_id", identifiers)

    def test_onem2m_resource_answer_uses_present_flags_exactly(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_onem2m_resource_answer({
            "query_device_id": "S123",
            "devices": [{
                "status": "resource_matches_found",
                "telemetry_record_count": 0,
            }],
            "required_resources": [
                "IDENTITY",
                "AE",
                "CIN",
                "URI_MAPPER",
            ],
            "resource_summary": {
                "IDENTITY": {
                    "present": False,
                    "matched_count": 0,
                    "direct_match_count": 0,
                    "related_match_count": 0,
                },
                "AE": {
                    "present": True,
                    "matched_count": 1,
                    "direct_match_count": 1,
                    "related_match_count": 0,
                },
                "CIN": {
                    "present": False,
                    "matched_count": 0,
                    "direct_match_count": 0,
                    "related_match_count": 0,
                    "command_count": 0,
                    "telemetry_count": 0,
                },
                "URI_MAPPER": {
                    "present": False,
                    "matched_count": 0,
                    "direct_match_count": 0,
                    "related_match_count": 0,
                },
            },
        })

        self.assertIn("IDENTITY: Missing", answer)
        self.assertIn("AE: Present", answer)
        self.assertIn("CIN: Missing", answer)
        self.assertIn("URI_MAPPER: Missing", answer)
        self.assertIn("incomplete OneM2M registration", answer)

    def test_ioa_v3_filters_placeholder_planner_params(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        params = agent.filter_tool_params(
            {
                "namespace": "default",
                "queue": "your_queue_name",
                "start": "start_time",
                "end": "2023-10-31T23:59:59Z",
                "step": "step_interval",
            },
            ["namespace", "queue", "start", "end", "step"],
            user_input="Check whether RabbitMQ queue messages are increasing linearly",
        )

        self.assertEqual(params, {"namespace": "default"})

    def test_ioa_v3_runbook_log_workflow_replaces_optional_grafana_slots(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        workflows = [
            {
                "tool": "get_company_onem2m_command_flow",
                "params": {"device_id": "dvi-1"},
                "reason": "command_flow",
                "confidence": 0.9,
                "planner": "semantic_llm",
                "tool_family": "company_db",
            },
            {
                "tool": "grafana_http_health",
                "params": {},
                "reason": "http_context",
                "confidence": 0.8,
                "planner": "semantic_llm",
                "tool_family": "grafana_n8n",
            },
            {
                "tool": "grafana_emqx_health",
                "params": {},
                "reason": "mqtt_context",
                "confidence": 0.8,
                "planner": "semantic_llm",
                "tool_family": "grafana_n8n",
            },
        ]

        planned = agent.ensure_runbook_required_workflows(
            workflows,
            (
                "Kịch bản 5 oneM2M device ID dvi-1 AE ID AE1 request ID req1; "
                "đọc log iot-http-api và iot-mqtt-client-adapter qua Loki"
            ),
        )

        tools = [workflow["tool"] for workflow in planned]
        self.assertEqual(len(tools), 3)
        self.assertIn("get_company_onem2m_command_flow", tools)
        self.assertIn("grafana_logs", tools)
        self.assertNotIn("grafana_emqx_health", tools)
        log_workflow = next(
            workflow for workflow in planned if workflow["tool"] == "grafana_logs"
        )
        self.assertNotIn("service", log_workflow["params"])
        self.assertEqual(log_workflow["params"]["level"], "error|warn")

    def test_ioa_v3_strips_trailing_punctuation_from_onem2m_ids(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        identifiers = agent.extract_onem2m_identifiers(
            "Device ID dvi-abc. AE ID ae-123. Request ID req-456."
        )

        self.assertEqual(identifiers["device_id"], "dvi-abc")
        self.assertEqual(identifiers["ae_id"], "ae-123")
        self.assertEqual(identifiers["request_id"], "req-456")

    def test_onem2m_identifier_candidates_can_be_derived_from_resources(self):
        candidates = collect_onem2m_identifier_candidates({
            "AE": {
                "samples": [{
                    "_id": "C-AE-device-1",
                    "aei": "AEI-device-1",
                }],
            },
            "CIN": {
                "command_samples": [{
                    "con": {
                        "requestId": "req-001",
                        "command": "turn_on",
                    },
                }],
            },
        })

        self.assertIn("C-AE-device-1", candidates["ae_id_candidates"])
        self.assertIn("AEI-device-1", candidates["ae_id_candidates"])
        self.assertIn("req-001", candidates["request_id_candidates"])

    def test_company_threshold_metric_filter_excludes_metadata(self):
        self.assertTrue(is_configured_threshold_metric("measurements[0].temperature"))
        self.assertTrue(is_configured_threshold_metric("tags[0].rssi"))
        self.assertFalse(is_configured_threshold_metric("timestamp"))
        self.assertFalse(is_configured_threshold_metric("locationId"))

    def test_ioa_v3_keeps_infra_prompts_on_grafana_route(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        cases = [
            ("check redis health", "grafana_redis_health"),
            ("company redis health", "grafana_redis_health"),
            ("platform service health", "grafana_platform_service_health"),
        ]

        for prompt, expected_tool in cases:
            with self.subTest(prompt=prompt):
                tool, _, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)

    def test_ioa_v3_company_db_tool_emits_query_commands(self):
        model = MagicMock()
        model.invoke.return_value.content = "Summary\nFound disconnected devices."
        model.invoke.return_value.response_metadata = {}
        agent = IOAV3LangGraphN8nAgent(model=model)

        with patch(
            "agents.ioa_v3_agent.get_company_disconnected_context",
            return_value={
                "source": "company_mongodb",
                "tool": "get_company_disconnected_devices",
                "db_audit_status": "runtime_audit_available",
                "db_audit": [{
                    "actor": "company-llm-tools",
                    "operation": "find",
                    "namespace": "devicemgmt.NODE",
                    "query": {"status": {"$in": ["disconnected", "offline"]}},
                    "projection": {"_id": 0, "rn": 1, "status": 1},
                    "effective_limit": 1000,
                    "max_time_ms": 5000,
                    "credentials_redacted": True,
                    "mutating": False,
                }],
                "count": 1,
                "devices": [{"device_id": "dev-1", "status": "disconnected"}],
            },
        ):
            events = list(agent.run_stream(
                "list disconnected devices",
                selected_source="company",
                source_resolution={
                    "selected_source": "company",
                    "active_source": "company_mongodb",
                },
                user_id=1,
            ))

        observations = [
            event for event in events
            if event.get("type") == "observation"
        ]
        db_step = next(
            execution
            for event in observations
            for execution in event["observation"]["output"].get("executions", [])
            if execution.get("tool") == "get_company_disconnected_devices"
        )
        self.assertIn("query_commands", db_step)
        self.assertIn(
            'db.getSiblingDB("devicemgmt").getCollection("NODE").find',
            db_step["query_commands"][0]["command"],
        )
        self.assertEqual(events[-1]["type"], "final")

    def test_ioa_v3_run_stream_emits_n8n_and_kpi_steps(self):
        model = MagicMock()
        model.invoke.return_value.content = "Summary\nRedis is healthy."
        model.invoke.return_value.response_metadata = {
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }
        }
        agent = IOAV3LangGraphN8nAgent(model=model)

        with patch(
            "agents.ioa_v3_agent.call_n8n_grafana_workflow",
            return_value={
                "final_answer": "n8n summary",
                "evidence": {
                    "level": "good",
                    "connected_clients": 10,
                    "hit_rate": 91.2,
                },
                "steps": [{
                    "thought": "Called Redis health endpoint.",
                    "action": "GET /grafana/redis",
                    "output": {"level": "good"},
                }],
                "token_usage": None,
                "request_payload": {
                    "workflow": {
                        "workflow_id": "redis_health",
                        "params": {},
                    }
                },
            },
        ):
            events = list(agent.run_stream(
                "check redis health",
                selected_source="company",
                source_resolution={
                    "selected_source": "company",
                    "active_source": "company_mongodb",
                },
                user_id=1,
            ))

        observations = [
            event for event in events
            if event.get("type") == "observation"
        ]
        self.assertTrue(any(
            execution.get("source") == "n8n_grafana_gateway"
            for event in observations
            for execution in event["observation"]["output"].get("executions", [])
        ))
        self.assertTrue(any(
            result.get("rule_source") == "config/grafana_kpi_rules.json"
            for event in observations
            for result in event["observation"]["output"].get("results", [])
        ))
        self.assertEqual(events[-1]["type"], "final")

    def test_ioa_v3_semantic_planner_runs_company_db_and_grafana_workflows(self):
        planner_response = MagicMock()
        planner_response.content = """
        {
          "confidence": 0.91,
          "reason": "Needs device evidence and Redis infrastructure health.",
          "workflows": [
            {
              "tool": "get_company_disconnected_devices",
              "params": {},
              "reason": "Find disconnected company devices first.",
              "confidence": 0.93
            },
            {
              "tool": "grafana_redis_health",
              "params": {},
              "reason": "Check Redis pressure that may affect device workflows.",
              "confidence": 0.88
            }
          ]
        }
        """
        planner_response.response_metadata = {}
        final_response = MagicMock()
        final_response.content = "Summary\nDisconnected devices and Redis health reviewed."
        final_response.response_metadata = {}
        model = MagicMock()
        model.invoke.side_effect = [planner_response, final_response]
        agent = IOAV3LangGraphN8nAgent(model=model)

        with patch(
            "agents.ioa_v3_agent.get_company_disconnected_context",
            return_value={
                "source": "company_mongodb",
                "tool": "get_company_disconnected_devices",
                "db_audit_status": "runtime_audit_available",
                "db_audit": [{
                    "actor": "company-llm-tools",
                    "operation": "find",
                    "namespace": "devicemgmt.NODE",
                    "query": {"status": {"$in": ["disconnected", "offline"]}},
                    "projection": {"_id": 0, "rn": 1, "status": 1},
                    "effective_limit": 1000,
                    "max_time_ms": 5000,
                    "credentials_redacted": True,
                    "mutating": False,
                }],
                "count": 1,
                "devices": [{"device_id": "dev-1", "status": "disconnected"}],
            },
        ), patch(
            "agents.ioa_v3_agent.call_n8n_grafana_workflow",
            return_value={
                "final_answer": "redis warning",
                "evidence": {"level": "warning", "hit_rate_percent": 47.2},
                "steps": [{
                    "thought": "Called Redis health endpoint.",
                    "action": "GET /grafana/redis",
                    "output": {"level": "warning"},
                }],
                "token_usage": None,
                "request_payload": {
                    "workflow": {
                        "workflow_id": "redis_health",
                        "params": {},
                    }
                },
            },
        ):
            events = list(agent.run_stream(
                "Check disconnected devices and whether Redis is unhealthy.",
                selected_source="company",
                source_resolution={
                    "selected_source": "company",
                    "active_source": "company_mongodb",
                },
                user_id=1,
            ))

        observations = [
            event for event in events
            if event.get("type") == "observation"
        ]
        selection = next(
            event["observation"]["output"]
            for event in observations
            if "planner" in event["observation"]["output"]
        )
        self.assertEqual(selection["planner"]["type"], "semantic_llm")
        run_step = next(
            event["observation"]["output"]
            for event in observations
            if event["observation"]["output"].get("workflow_count") == 2
        )
        tools = [item["tool"] for item in run_step["executions"]]
        self.assertEqual(
            tools,
            ["get_company_disconnected_devices", "grafana_redis_health"],
        )
        self.assertEqual(events[-1]["type"], "final")

    def test_ioa_v3_semantic_planner_token_usage_is_counted(self):
        planner_response = MagicMock()
        planner_response.content = """
        {
          "confidence": 0.91,
          "reason": "Needs resource evidence.",
          "workflows": [
            {
              "tool": "get_company_onem2m_device_resources",
              "params": {"device_id": "dev-1"},
              "reason": "Check required resources.",
              "confidence": 0.93
            }
          ]
        }
        """
        planner_response.response_metadata = {
            "token_usage": {
                "prompt_tokens": 20,
                "completion_tokens": 7,
                "total_tokens": 27,
            }
        }
        model = MagicMock()
        model.invoke.return_value = planner_response
        agent = IOAV3LangGraphN8nAgent(model=model)

        workflows, metadata = agent.plan_workflows_semantically(
            "Check OneM2M resources for dev-1."
        )

        self.assertEqual(
            workflows[0]["tool"],
            "get_company_onem2m_device_resources",
        )
        self.assertEqual(metadata["token_usage"]["total_tokens"], 27)

    def test_ioa_v3_deterministic_answer_preserves_prior_token_usage(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        state = {
            "selected_tool": "get_company_onem2m_device_resources",
            "token_usage": {
                "input_tokens": 20,
                "output_tokens": 7,
                "total_tokens": 27,
                "source": "openai_response_metadata",
            },
            "steps": [],
            "tool_outputs": [{
                "tool": "get_company_onem2m_device_resources",
                "result": {
                    "query_device_id": "dev-1",
                    "resource_summary": {
                        "IDENTITY": {"present": False, "matched_count": 0},
                        "AE": {"present": True, "matched_count": 1},
                        "CNT": {"present": True, "matched_count": 2},
                        "CIN": {"present": False, "matched_count": 0},
                        "SUBSCRIPTION": {"present": True, "matched_count": 1},
                        "URI_MAPPER": {"present": False, "matched_count": 0},
                    },
                },
            }],
        }

        result = agent.generate_answer_node(state)

        self.assertEqual(result["token_usage"]["total_tokens"], 27)
        self.assertIn("IDENTITY: Missing", result["final_answer"])

    def test_ioa_v3_combines_planner_and_answer_token_usage(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        usage = agent.combine_token_usage(
            {
                "input_tokens": 20,
                "output_tokens": 7,
                "total_tokens": 27,
                "source": "planner",
            },
            {
                "input_tokens": 30,
                "output_tokens": 9,
                "total_tokens": 39,
                "source": "answer",
            },
        )

        self.assertEqual(usage["input_tokens"], 50)
        self.assertEqual(usage["output_tokens"], 16)
        self.assertEqual(usage["total_tokens"], 66)
        self.assertEqual(usage["source"], "ioa_v3_graph")

    def test_ioa_v3_answer_evidence_keeps_concrete_samples(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        state = {
            "tool_outputs": [
                {
                    "source": "company_mongodb",
                    "tool": "get_company_disconnected_devices",
                    "result": {
                        "count": 1,
                        "db_audit_status": "runtime_audit_available",
                        "devices": [{
                            "device_id": "dev-1",
                            "device_name": "Gateway A",
                            "status": "disconnected",
                            "metrics": [{"name": "temperature", "value": 72}],
                        }],
                    },
                    "query_commands": [{
                        "namespace": "devicemgmt.NODE",
                        "command": "db.getSiblingDB(\"devicemgmt\")",
                    }],
                },
                {
                    "source": "n8n_grafana_gateway",
                    "tool": "grafana_redis_health",
                    "http_call": {"method": "GET", "path": "/grafana/redis"},
                    "result": {
                        "source": "grafana_dashboard_client",
                        "level": "warning",
                        "body": {
                            "connected_clients": 84,
                            "hit_rate_percent": 47.2,
                        },
                    },
                },
            ],
        }

        evidence = agent.build_answer_evidence(state)

        self.assertEqual(evidence["workflow_count"], 2)
        self.assertEqual(
            evidence["results"][0]["devices"][0]["device_name"],
            "Gateway A",
        )
        self.assertEqual(
            evidence["results"][0]["devices"][0]["metrics"][0]["value"],
            72,
        )
        self.assertEqual(
            evidence["results"][1]["body"]["hit_rate_percent"],
            47.2,
        )

    def test_ioa_v3_answer_evidence_keeps_telemetry_coverage_counts(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        state = {
            "user_input": "/coverage",
            "selected_tool": "get_company_telemetry_coverage",
            "tool_outputs": [{
                "source": "company_mongodb",
                "tool": "get_company_telemetry_coverage",
                "result": {
                    "device_count": 31,
                    "devices_with_telemetry": 5,
                    "inventory_only_devices": 26,
                    "unmapped_telemetry_count": 374,
                    "top_metric_fields": [
                        {"name": "batteryVoltage", "device_count": 1},
                        {"name": "pressure", "device_count": 1},
                    ],
                    "sample_devices_with_telemetry": [{
                        "device_id": "dev-1",
                        "device_name": "SmartAsset_9b47fedc",
                        "status": "disconnected",
                        "telemetry_record_count": 43,
                        "metrics": [{"name": "pressure", "value": 3.1}],
                    }],
                },
                "query_commands": [{
                    "namespace": "datamgmt.CIN",
                    "command": "db.getSiblingDB(\"datamgmt\")",
                }],
            }],
        }

        evidence = agent.build_answer_evidence(state)
        result = evidence["results"][0]

        self.assertEqual(result["device_count"], 31)
        self.assertEqual(result["devices_with_telemetry"], 5)
        self.assertEqual(result["inventory_only_devices"], 26)
        self.assertEqual(result["unmapped_telemetry_count"], 374)
        self.assertEqual(result["top_metric_fields"][0]["name"], "batteryVoltage")
        self.assertEqual(
            result["sample_devices_with_telemetry"][0]["device_name"],
            "SmartAsset_9b47fedc",
        )

        prompt = agent.build_answer_prompt(state)
        self.assertIn("SmartAsset_9b47fedc", prompt)
        self.assertIn("disconnected", prompt)
        self.assertIn("pressure", prompt)

    def test_ioa_v3_answer_prompt_includes_kpi_and_preview_data_guardrails(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        state = {
            "user_input": "check platform health",
            "selected_tool": "grafana_platform_service_health",
            "tool_outputs": [],
        }

        prompt = agent.build_answer_prompt(state)

        self.assertIn("Core service-quality signals first", prompt)
        self.assertIn("Infrastructure as diagnostic supporting evidence", prompt)
        self.assertIn("company DB evidence as preview/test data", prompt)


if __name__ == "__main__":
    unittest.main()
