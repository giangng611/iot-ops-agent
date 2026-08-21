import os
import json
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
from services.prompt_service import DEFAULT_PROMPTS, list_prompts
from services.n8n_gateway_service import (
    DEFAULT_N8N_V3_WEBHOOK_URL,
    build_n8n_v3_payload,
    get_n8n_v3_webhook_url,
)
from services import mcp_observability_service


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
        connection_tool = get_grafana_tool_by_name("grafana_emqx_connection_trend")
        self.assertNotIn("device_id", connection_tool["allowed_params"])

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
                "Check Kubernetes resource health in namespace iot-platform: pod CPU and memory",
                "grafana_k8s_resources",
            ),
        ]

        for prompt, expected_tool in cases:
            with self.subTest(prompt=prompt):
                tool, _, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)

    def test_ioa_v3_routes_runbook_scenarios_8_to_12(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        cases = [
            (
                "Find the top 10 RabbitMQ queues by message backlog in namespace test and flag any queue above 10000 messages.",
                "grafana_queue_backlog",
                {"namespace": "test", "topk": 10, "threshold": 10000},
            ),
            (
                "Check whether RabbitMQ queue messages are increasing linearly over the requested time range.",
                "grafana_queue_trend",
                {},
            ),
            (
                "Check whether EMQX messages dropped increased over the requested time range.",
                "grafana_emqx_dropped_trend",
                {},
            ),
            (
                "Check EMQX client connected and disconnected rates to detect reconnect loops.",
                "grafana_emqx_connection_trend",
                {},
            ),
            (
                "Check Kubernetes resource health in namespace iot-platform: pod CPU, memory, restart count, pod status, node resources.",
                "grafana_k8s_resources",
                {"namespace": "iot-platform"},
            ),
        ]

        for prompt, expected_tool, expected_params in cases:
            with self.subTest(prompt=prompt):
                tool, params, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)
                for key, value in expected_params.items():
                    self.assertEqual(params.get(key), value)

    def test_ioa_v3_metric_runbook_override_keeps_dropped_trend_primary(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        prompt = (
            "Check whether EMQX messages dropped increased over the requested "
            "time range. Use sum(emqx_messages_dropped{namespace=\"emqx\",job=\"emqx\"}) "
            "and then recommend checking EMQX logs, MQTT adapter logs, broker "
            "CPU/memory, connection count, queue backlog, and core service errors."
        )

        workflows = agent.ensure_runbook_required_workflows(
            [
                {
                    "tool": "grafana_emqx_health",
                    "params": {},
                    "reason": "semantic_emqx_health",
                    "confidence": 0.7,
                    "planner": "semantic_llm",
                    "tool_family": "grafana_n8n",
                },
                {
                    "tool": "grafana_queue_backlog",
                    "params": {"namespace": "test"},
                    "reason": "queue_backlog_keyword",
                    "confidence": 0.6,
                    "planner": "keyword",
                    "tool_family": "grafana_n8n",
                },
            ],
            prompt,
        )

        self.assertEqual(workflows[0]["tool"], "grafana_emqx_dropped_trend")
        self.assertEqual(workflows[0]["planner"], "runbook_keyword_override")

    def test_ioa_v3_reconnect_runbook_does_not_treat_candidates_as_device(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        prompt = (
            "Check EMQX client connected and disconnected rates to detect "
            "onboarding spikes or reconnect loops. Do not require a device_id "
            "from the operator; derive affected device candidates from EMQX or "
            "MQTT adapter evidence when available."
        )

        self.assertIsNone(agent.extract_device_identifier(prompt))

        workflows = agent.ensure_runbook_required_workflows(
            [{
                "tool": "get_company_onem2m_device_resources",
                "params": {"device_id": "candidates"},
                "reason": "semantic_resource_guess",
                "confidence": 0.6,
                "planner": "semantic_llm",
                "tool_family": "company_db",
            }],
            prompt,
        )

        self.assertEqual(workflows[0]["tool"], "grafana_emqx_connection_trend")
        self.assertEqual(workflows[0]["planner"], "runbook_keyword_override")

    def test_ioa_v3_reconnect_runbook_with_log_next_actions_stays_metric_first(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        prompt = (
            "Check EMQX client connected and disconnected rates to detect "
            "onboarding spikes or reconnect loops. Do not require a device_id "
            "from the operator; derive affected device candidates from EMQX or "
            "MQTT adapter evidence when available. Use "
            "sum(rate(emqx_client_connected{namespace=\"emqx\",job=\"emqx\"}[1m])) "
            "and sum(rate(emqx_client_disconnected{namespace=\"emqx\",job=\"emqx\"}[1m])). "
            "Then suggest MQTT adapter log, device resource, previous-error-log, "
            "and EMQX broker follow-up."
        )

        tool, params, reason = agent.classify_tool(prompt)

        self.assertEqual(tool, "grafana_emqx_connection_trend")
        self.assertEqual(params, {})
        self.assertEqual(reason, "emqx_connection_trend_keywords")

    def test_ioa_v3_executes_runbook_metric_tools_through_mcp(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        workflow = {
            "tool": "grafana_queue_backlog",
            "params": {"namespace": "test", "topk": 10, "threshold": 10000},
            "reason": "scenario_8",
            "confidence": 0.9,
        }

        with patch(
            "agents.ioa_v3_agent.query_iot_platform_metric_via_mcp",
            return_value={
                "source": "mcp_server",
                "mcp_tool": "grafana_query",
                "tool": "grafana_queue_backlog",
                "request": workflow["params"],
                "promql_query": 'topk(10, sum by (queue) (rabbitmq_queue_messages{namespace="test",job="monitoring/rabbitmq"}))',
                "result": {"data": {"result": []}},
            },
        ) as query_metric, patch(
            "agents.ioa_v3_agent.call_n8n_grafana_workflow"
        ) as n8n_call:
            execution = agent.execute_grafana_workflow(
                {"user_input": "scenario 8", "source_resolution": {}},
                workflow,
            )

        query_metric.assert_called_once_with(
            "grafana_queue_backlog",
            workflow["params"],
        )
        n8n_call.assert_not_called()
        self.assertEqual(execution["tool_output"]["source"], "mcp_server")
        self.assertEqual(execution["tool_output"]["mcp_tool"], "grafana_query")

    def test_ioa_v3_metric_runbooks_do_not_treat_empty_samples_as_normal(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        cases = [
            (
                "grafana_queue_trend",
                {
                    "request": {"namespace": "test", "start": 1, "end": 2, "step": 300},
                    "promql_query": 'sum by (queue) (rabbitmq_queue_messages{namespace="test",job="monitoring/rabbitmq"})',
                    "result": {"data": {"result": []}},
                },
                "insufficient metric evidence",
            ),
            (
                "grafana_emqx_connection_trend",
                {
                    "request": {"device_scope": "all", "start": 1, "end": 2, "step": 300},
                    "queries": {
                        "connected": {"promql_query": "connected", "data": {"result": []}},
                        "disconnected": {"promql_query": "disconnected", "data": {"result": []}},
                    },
                },
                "insufficient metric evidence",
            ),
            (
                "grafana_k8s_resources",
                {
                    "request": {"namespace": "iot-platform"},
                    "queries": {
                        "pod_cpu": {"data": {"result": []}},
                        "pod_memory": {"data": {"result": []}},
                        "pod_restarts": {"data": {"result": []}},
                        "pod_status": {"data": {"result": []}},
                    },
                },
                "returned no Kubernetes resource samples",
            ),
        ]

        for tool, result, expected in cases:
            with self.subTest(tool=tool):
                answer = agent.build_metric_runbook_answer(result, tool, "")
                self.assertIn(expected, answer)
                self.assertNotIn("near zero or only slightly elevated", answer)
                self.assertNotIn("No restart count above threshold", answer)

    def test_ioa_v3_metric_parser_reads_grafana_dataframe_results(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        result = {
            "request": {"namespace": "test", "topk": 10, "threshold": 10000},
            "promql_query": 'topk(10, sum by (queue) (rabbitmq_queue_messages{namespace="test",job="monitoring/rabbitmq"}))',
            "result": {
                "results": {
                    "test": {
                        "frames": [{
                            "schema": {
                                "fields": [
                                    {"name": "Time", "type": "time"},
                                    {
                                        "name": "rabbitmq_queue_messages",
                                        "type": "number",
                                        "labels": {"queue": "queue.onem2m.datamgmt"},
                                    },
                                ],
                            },
                            "data": {
                                "values": [
                                    [1783413210000, 1783413240000],
                                    [12, 15],
                                ],
                            },
                        }],
                    },
                },
            },
        }

        answer = agent.build_metric_runbook_answer(
            result,
            "grafana_queue_backlog",
            "",
        )

        self.assertIn("queue.onem2m.datamgmt", answer)
        self.assertIn("15 messages", answer)
        self.assertNotIn("No queues were returned", answer)

    def test_ioa_v3_infrastructure_overview_requires_all_five_tools(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        workflows = agent.ensure_infrastructure_overview_workflows(
            [
                {
                    "tool": "grafana_k8s_health",
                    "params": {},
                    "reason": "semantic",
                    "confidence": 0.6,
                    "planner": "semantic_llm",
                    "tool_family": "grafana_n8n",
                },
                {
                    "tool": "grafana_redis_health",
                    "params": {},
                    "reason": "semantic",
                    "confidence": 0.6,
                    "planner": "semantic_llm",
                    "tool_family": "grafana_n8n",
                },
            ],
            "Check Kubernetes, Linux node, Redis, MongoDB, and MySQL health as diagnostic evidence for platform issues.",
        )

        self.assertEqual(
            [workflow["tool"] for workflow in workflows],
            [
                "grafana_k8s_health",
                "grafana_linux_health",
                "grafana_redis_health",
                "grafana_mongodb_health",
                "grafana_mysql_health",
            ],
        )

    def test_ioa_v3_infrastructure_overview_tools_use_mcp(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        workflow = {
            "tool": "grafana_linux_health",
            "params": {},
            "reason": "infra",
            "confidence": 0.7,
        }

        with patch(
            "agents.ioa_v3_agent.query_iot_platform_metric_via_mcp",
            return_value={
                "source": "mcp_server",
                "mcp_tool": "grafana_query",
                "tool": "grafana_linux_health",
                "request": {},
                "queries": {},
            },
        ) as query_metric, patch(
            "agents.ioa_v3_agent.call_n8n_grafana_workflow"
        ) as n8n_call:
            execution = agent.execute_grafana_workflow(
                {"user_input": "infra", "source_resolution": {}},
                workflow,
            )

        query_metric.assert_called_once_with("grafana_linux_health", {})
        n8n_call.assert_not_called()
        self.assertEqual(execution["tool_output"]["source"], "mcp_server")

    def test_ioa_v3_runbook_metric_answer_uses_standard_format(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        state = {
            "selected_tool": "grafana_queue_backlog",
            "user_input": "scenario 8",
            "tool_outputs": [{
                "tool": "grafana_queue_backlog",
                "source": "mcp_server",
                "result": {
                    "source": "mcp_server",
                    "tool": "grafana_queue_backlog",
                    "request": {
                        "namespace": "test",
                        "topk": 10,
                        "threshold": 10000,
                    },
                    "promql_query": 'topk(10, sum by (queue) (rabbitmq_queue_messages{namespace="test",job="monitoring/rabbitmq"}))',
                    "result": {
                        "data": {
                            "result": [{
                                "metric": {"queue": "queue.telemetry.ingest"},
                                "value": [1710000000, "12001"],
                            }]
                        }
                    },
                },
            }],
        }

        answer = agent.build_deterministic_answer(state)

        self.assertIn("# RabbitMQ Queue Backlog Check Result", answer)
        self.assertIn("## 2. Input", answer)
        self.assertIn("## 5. System Metrics", answer)
        self.assertIn("queue.telemetry.ingest", answer)
        self.assertIn("**Status:** abnormal", answer)

    def test_queue_backlog_followups_follow_english_prompt_language(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_queue_backlog_answer(
            {
                "request": {
                    "namespace": "test",
                    "topk": 10,
                    "threshold": 10000,
                },
                "promql_query": "topk(10, rabbitmq_queue_messages)",
                "result": {
                    "data": {
                        "result": [{
                            "metric": {
                                "queue": "amq.gen-Hfwxk4whD_ROGgw6hkYYTA",
                            },
                            "value": [1710000000, "0"],
                        }]
                    }
                },
            },
            "Find the top 10 RabbitMQ queues by message backlog in namespace test.",
        )

        self.assertIn(
            "Show details for queue <queue_id>",
            answer,
        )
        self.assertIn(
            "Check whether queue <queue_id> is increasing",
            answer,
        )
        self.assertIn("Check K8s resources for consumer pods in namespace test", answer)
        self.assertNotIn("Chi tiết", answer)
        self.assertNotIn("Kiểm tra", answer)
        self.assertNotIn("có đang", answer)

    def test_queue_consumer_k8s_followup_routes_to_k8s_resources(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, _ = agent.classify_tool(
            "Check K8s resources for consumer pods in namespace test"
        )

        self.assertEqual(tool, "grafana_k8s_resources")
        self.assertEqual(params.get("namespace"), "test")

    def test_k8s_namespace_label_followup_routes_to_resource_formatter(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, _ = agent.classify_tool(
            "Check the Kubernetes metric scrape targets for the test namespace."
        )

        self.assertEqual(tool, "grafana_k8s_resources")
        self.assertEqual(params.get("namespace"), "test")

        tool, params, _ = agent.classify_tool(
            "Check the namespace label configuration for the test namespace."
        )

        self.assertEqual(tool, "grafana_k8s_resources")
        self.assertEqual(params.get("namespace"), "test")

    def test_k8s_normal_resource_answer_does_not_suggest_scrape_followup(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        answer = agent.build_k8s_resource_answer(
            {
                "request": {"namespace": "test"},
                "queries": {
                    "pod_cpu": {
                        "data": {
                            "result": [{
                                "metric": {"pod": "rabbitmq-0"},
                                "value": [1, "0.08"],
                            }]
                        }
                    },
                    "pod_memory": {
                        "data": {
                            "result": [{
                                "metric": {"pod": "rabbitmq-0"},
                                "value": [1, str(266 * 1024 * 1024)],
                            }]
                        }
                    },
                    "pod_restarts": {
                        "data": {
                            "result": [{
                                "metric": {"pod": "rabbitmq-0"},
                                "value": [1, "0"],
                            }]
                        }
                    },
                    "node_memory": {
                        "data": {
                            "result": [{
                                "metric": {"instance": "node-a"},
                                "value": [1, "68"],
                            }]
                        }
                    },
                },
            },
            "Monitor CPU and memory usage for the consumer pods.",
        )

        self.assertIn("## 7. Recommended Next Action", answer)
        self.assertIn("No action needed", answer)
        self.assertNotIn("Verify Kubernetes metric scrape targets", answer)
        self.assertNotIn("## Follow-up Questions", answer)

    def test_specific_queue_trend_followup_keeps_queue_and_continues_drilldown(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        prompt = "check if queue amq.gen-_3a1nCYXQe43CHK8JXHSSg is increasing?"

        tool, params, _ = agent.classify_tool(prompt)

        self.assertEqual(tool, "grafana_queue_trend")
        self.assertEqual(params.get("queue"), "amq.gen-_3a1nCYXQe43CHK8JXHSSg")

        answer = agent.build_queue_trend_answer(
            {
                "request": {
                    "namespace": "test",
                    "queue": "amq.gen-_3a1nCYXQe43CHK8JXHSSg",
                    "start": 1784601302,
                    "end": 1784604902,
                    "step": 300,
                },
                "promql_query": "sum by (queue) (rabbitmq_queue_messages)",
                "result": {
                    "data": {
                        "result": [{
                            "metric": {
                                "queue": "amq.gen-_3a1nCYXQe43CHK8JXHSSg",
                            },
                            "values": [
                                [1784601302, "0"],
                                [1784604902, "0"],
                            ],
                        }]
                    }
                },
            },
            prompt,
        )

        self.assertIn("Show details for queue amq.gen-_3a1nCYXQe43CHK8JXHSSg", answer)
        self.assertIn("Check K8s resources for consumer pods in namespace test", answer)
        self.assertIn("Check RabbitMQ throughput in namespace test", answer)

    def test_specific_queue_trend_answer_does_not_show_other_queue_rows(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        requested_queue = "amq.gen-WweYSoCJiV6Tc00Hl7rQNg"

        answer = agent.build_queue_trend_answer(
            {
                "request": {
                    "namespace": "test",
                    "queue": requested_queue,
                    "start": 1784703734,
                    "end": 1784707334,
                    "step": 300,
                },
                "promql_query": "sum by (queue) (rabbitmq_queue_messages)",
                "result": {
                    "data": {
                        "result": [{
                            "metric": {"queue": "amq.gen-3kobT6PQt9MOg3rNMvoJ1Q"},
                            "values": [
                                [1784703734, "0"],
                                [1784707334, "0"],
                            ],
                        }]
                    }
                },
            },
            f"Check whether queue {requested_queue} is increasing",
        )

        self.assertIn(f"no RabbitMQ queue range samples for `{requested_queue}`", answer)
        self.assertIn("_No range samples returned in evidence._", answer)
        self.assertNotIn("amq.gen-3kobT6PQt9MOg3rNMvoJ1Q", answer)

    def test_mcp_specific_queue_trend_query_filters_promql_by_queue(self):
        with patch.object(
            mcp_observability_service,
            "_query_prometheus_range",
            return_value={"start": 1, "end": 2, "step": 300, "result": {"data": {"result": []}}},
        ) as query_range:
            evidence = mcp_observability_service.query_iot_platform_metric_via_mcp(
                "grafana_queue_trend",
                {
                    "namespace": "test",
                    "queue": "amq.gen-WweYSoCJiV6Tc00Hl7rQNg",
                },
            )

        promql = query_range.call_args.args[0]
        self.assertIn('queue="amq.gen-WweYSoCJiV6Tc00Hl7rQNg"', promql)
        self.assertEqual(
            evidence["request"]["queue"],
            "amq.gen-WweYSoCJiV6Tc00Hl7rQNg",
        )

    def test_queue_related_error_followup_routes_to_loki_keyword(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, reason = agent.classify_tool(
            "Check for database connection errors related to queue "
            "amq.gen-kCkv6qO7vrYrylIcFfhXsw."
        )

        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params.get("contains"), "amq.gen-kCkv6qO7vrYrylIcFfhXsw")
        self.assertEqual(reason, "queue_related_error_logs")

    def test_consumer_pod_logs_followup_does_not_parse_logs_as_pod_name(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, _ = agent.classify_tool("Show details for consumer pod logs.")

        self.assertEqual(tool, "grafana_k8s_resources")
        self.assertEqual(params.get("namespace"), "test")
        self.assertNotEqual(params.get("pod"), "logs")
        self.assertNotIn("pod", params)

    def test_followup_planner_rewrites_consumer_pod_logs_to_k8s_resources(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Planner used vague consumer pod logs wording.",
            "questions": [
                "Show details for consumer pod logs.",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# RabbitMQ Queue Trend Check Result",
                "",
                "## 7. Recommended Next Action",
                "- Check consumer pods, queue-processing service logs, CPU/memory, and database or broker connection errors.",
            ]),
            {
                "selected_tool": "grafana_queue_trend",
                "user_input": "Check whether queue amq.gen-kCkv6qO7vrYrylIcFfhXsw is increasing.",
                "conversation_context": [],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Check K8s resources for consumer pods in namespace test", followups)
        self.assertNotIn("consumer pod logs", followups)

    def test_emqx_reconnect_answer_uses_concrete_log_followups(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_emqx_connection_answer(
            {
                "request": {
                    "start": 1,
                    "end": 2,
                    "step": 300,
                },
                "queries": {
                    "connected": {
                        "promql_query": "connected",
                        "data": {
                            "result": [{
                                "metric": {"instance": "emqx-0"},
                                "values": [[1, "0"], [2, "0"]],
                            }]
                        },
                    },
                    "disconnected": {
                        "promql_query": "disconnected",
                        "data": {
                            "result": [{
                                "metric": {"instance": "emqx-0"},
                                "values": [[1, "0"], [2, "0"]],
                            }]
                        },
                    },
                },
            },
            "Check EMQX client connected and disconnected rates",
        )

        self.assertIn("Check MQTT adapter logs for reconnect evidence", answer)
        self.assertIn("Check EMQX logs for errors or warnings", answer)
        self.assertNotIn("inspect error logs before reconnect events", answer.lower())

    def test_metric_prompt_next_action_terms_do_not_block_mqtt_followup(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Planner omitted MQTT even though the answer recommended it.",
            "questions": [
                "Check EMQX logs for errors or warnings",
                "Review broker CPU/memory usage and connection count",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# EMQX Connect/Disconnect Check Result",
                "",
                "## 6. Conclusion",
                "No reconnect loop or onboarding spike detected in current metric evidence.",
                "",
                "## 7. Recommended Next Action",
                "Check MQTT adapter logs for reconnect evidence, check EMQX logs "
                "for broker-side errors, and review EMQX broker health only if "
                "reconnect symptoms persist.",
            ]),
            {
                "selected_tool": "grafana_emqx_connection_trend",
                "user_input": (
                    "Check EMQX client connected and disconnected rates to detect "
                    "onboarding spikes or reconnect loops. Then suggest MQTT "
                    "adapter log, device resource, previous-error-log, and EMQX "
                    "broker follow-up."
                ),
                "conversation_context": [],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Check MQTT adapter logs for reconnect evidence", followups)
        self.assertIn("Check EMQX logs for errors or warnings", followups)
        self.assertIn("Review broker CPU/memory usage and connection count", followups)

    def test_queue_detail_and_throughput_answers_continue_drilldown(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        detail_answer = agent.build_queue_detail_answer(
            {
                "request": {
                    "queue_name": "amq.gen-KcepRTvyR1eqjJ6h-WFpNg",
                },
                "queries": {
                    "messages": {"data": {"result": [{"value": [1, "0"]}]}},
                    "consumers": {"data": {"result": [{"value": [1, "1"]}]}},
                },
            },
            "Show details for queue amq.gen-KcepRTvyR1eqjJ6h-WFpNg",
        )

        self.assertIn("## Follow-up Questions", detail_answer)
        self.assertIn(
            "Check whether queue amq.gen-KcepRTvyR1eqjJ6h-WFpNg is increasing",
            detail_answer,
        )
        self.assertIn("RabbitMQ throughput", detail_answer)

        throughput_answer = agent.build_throughput_answer(
            {
                "source": "mcp_server",
                "mcp_tool": "grafana_query",
                "queries": {
                    "publish_rate": {"data": {"result": [{"value": [1, "0"]}]}},
                    "ack_rate": {"data": {"result": [{"value": [1, "5.53"]}]}},
                    "delivery_rate": {"data": {"result": [{"value": [1, "5.53"]}]}},
                    "queue_depth": {"data": {"result": [{"value": [1, "0"]}]}},
                },
            },
            "RabbitMQ throughput",
        )

        self.assertNotIn("## Follow-up Questions", throughput_answer)
        self.assertIn("No action needed", throughput_answer)

    def test_followup_planner_replaces_static_queue_followups_with_placeholder(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Queue candidates were listed and details are the next drilldown.",
            "questions": [
                "Show details for queue <queue_id>",
                "Check whether queue <queue_id> is increasing",
            ],
        })
        response.response_metadata = {
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
            }
        }
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, usage = agent.apply_followup_planner(
            "\n".join([
                "# RabbitMQ Queue Backlog Check Result",
                "",
                "## 7. Recommended Next Action",
                "Check consumers if backlog continues to grow.",
                "",
                "## Follow-up Questions",
                "- Show details for queue amq.gen-old",
            ]),
            {
                "user_input": "Find the top 10 RabbitMQ queues by message backlog.",
                "selected_tool": "grafana_queue_backlog",
                "tool_outputs": [],
            },
        )

        self.assertIn("Show details for queue <queue_id>", answer)
        self.assertIn("Check whether queue <queue_id> is increasing", answer)
        self.assertNotIn("amq.gen-old", answer)
        self.assertEqual(usage["total_tokens"], 14)

    def test_followup_planner_parameterizes_fixed_queue_candidates(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "The planner chose one queue, but the answer listed candidates.",
            "questions": [
                "Check consumers for queue `amq.gen-3kobT6PQt9MOg3rNMvoJ1Q`.",
                "Review error logs associated with queue `amq.gen-3kobT6PQt9MOg3rNMvoJ1Q`.",
            ],
        })
        response.response_metadata = {}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# RabbitMQ Queue Backlog Check Result",
                "",
                "## 5. System Metrics",
                "| Queue | Messages |",
                "|---|---|",
                "| `amq.gen-3kobT6PQt9MOg3rNMvoJ1Q` | 0 |",
                "| `queue.onem2m.httpapi` | 0 |",
                "",
                "## 7. Recommended Next Action",
                "Check consumers, queue-processing services, related error logs, and throughput if backlog continues to grow.",
            ]),
            {
                "user_input": "Find the top 10 RabbitMQ queues by message backlog.",
                "selected_tool": "grafana_queue_backlog",
                "tool_outputs": [],
            },
        )

        self.assertIn("Check consumers for queue <queue_id>.", answer)
        self.assertIn("Review error logs associated with queue <queue_id>.", answer)
        self.assertNotIn("amq.gen-3kobT6PQt9MOg3rNMvoJ1Q", answer.split("## Follow-up Questions")[-1])

    def test_followup_planner_rewrites_generic_service_logs_to_concrete_checks(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "The answer asks for service log evidence.",
            "questions": [
                "Review queue-processing service logs for errors.",
                "Correlate with adjacent service logs for `requested service`.",
            ],
        })
        response.response_metadata = {}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# RabbitMQ Queue Trend Check Result",
                "",
                "## 6. Conclusion",
                "There is not enough evidence to conclude continuous consumer congestion.",
                "",
                "## 7. Recommended Next Action",
                "Check consumer pods, queue-processing service logs, CPU/memory, and database or broker connection errors.",
            ]),
            {
                "user_input": "Check whether RabbitMQ queue messages are increasing linearly.",
                "selected_tool": "grafana_queue_trend",
                "tool_outputs": [],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Check RabbitMQ throughput", followups)
        self.assertNotIn("requested service", followups)
        self.assertNotIn("<service>", followups)

    def test_followup_planner_suppresses_no_action_needed_followups(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": False,
            "reason": "The answer says no action is needed.",
            "questions": [],
        })
        response.response_metadata = {}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# RabbitMQ Throughput Check Result",
                "",
                "## 4. Recommended Next Action",
                "No action needed. Monitor periodically if telemetry freshness complaints recur.",
                "",
                "## Follow-up Questions",
                "- Check RabbitMQ queue backlog in namespace test",
            ]),
            {
                "user_input": "RabbitMQ throughput",
                "selected_tool": "grafana_throughput",
                "tool_outputs": [],
            },
        )

        self.assertIn("No action needed", answer)
        self.assertNotIn("Follow-up Questions", answer)
        self.assertNotIn("Check RabbitMQ queue backlog", answer)

    def test_followup_planner_suppresses_completed_action_paraphrases(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Move to unresolved evidence branches only.",
            "questions": [
                "Review broker CPU/memory usage metrics in detail.",
                "Review the EMQX broker pods for performance metrics.",
                "Check MQTT adapter logs for any issues.",
                "Check RabbitMQ queue backlog.",
            ],
        })
        response.response_metadata = {}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# EMQX Broker Health Check Result",
                "",
                "## 6. Conclusion",
                "Broker is showing signs of stress.",
                "",
                "## 7. Recommended Next Action",
                "Check EMQX logs, MQTT adapter logs, broker CPU/memory, "
                "connection count, queue backlog, and core service error logs.",
            ]),
            {
                "user_input": "Review broker CPU/memory usage and connection count.",
                "selected_tool": "grafana_emqx_health",
                "tool_outputs": [],
                "conversation_context": [
                    {
                        "role": "user",
                        "content": "Review broker CPU/memory usage and connection count.",
                    },
                    {
                        "role": "assistant",
                        "content": "# EMQX Broker Health Check Result\nBroker status: abnormal",
                    },
                ],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertNotIn("CPU/memory", followups)
        self.assertNotIn("broker pods", followups)
        self.assertIn("Check MQTT adapter logs for any issues", followups)

    def test_followup_planner_fills_required_emqx_runbook_branches(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Planner omitted log branches.",
            "questions": [
                "Review broker CPU/memory usage during the specified time range.",
                "Check RabbitMQ throughput.",
            ],
        })
        response.response_metadata = {}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# EMQX Dropped Messages Check Result",
                "",
                "## 6. Conclusion",
                "Delta=0 — no new drops in this window.",
                "",
                "## 7. Recommended Next Action",
                "Check EMQX logs, MQTT adapter logs, broker CPU/memory, "
                "connection count, queue backlog, and core service error logs.",
            ]),
            {
                "user_input": (
                    "Check whether EMQX messages dropped increased over the requested time range."
                ),
                "selected_tool": "grafana_emqx_dropped_trend",
                "tool_outputs": [],
                "conversation_context": [],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Check EMQX logs for errors or warnings", followups)
        self.assertIn("Check MQTT adapter logs for any issues", followups)
        self.assertIn("Review broker CPU/memory usage", followups)

    def test_followup_planner_can_return_four_emqx_branches(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Required EMQX branches are still open.",
            "questions": [],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# EMQX Dropped Messages Check Result",
                "",
                "## 7. Recommended Next Action",
                "Check EMQX logs, MQTT adapter logs, broker CPU/memory, "
                "connection count, queue backlog, and core service error logs.",
            ]),
            {
                "selected_tool": "grafana_emqx_dropped_trend",
                "user_input": (
                    "Check whether EMQX messages dropped increased over the requested time range."
                ),
                "conversation_context": [],
            },
        )

        followup_lines = [
            line for line in answer.splitlines()
            if line.startswith("- ")
        ]
        followups = answer.split("## Follow-up Questions")[-1]
        self.assertEqual(len(followup_lines), 4)
        self.assertIn("Check EMQX logs for errors or warnings", followups)
        self.assertIn("Check MQTT adapter logs for any issues", followups)
        self.assertIn("Review broker CPU/memory usage and connection count", followups)
        self.assertIn("Check RabbitMQ queue backlog", followups)
        self.assertNotIn("Show current EMQX connection count", followups)

    def test_followup_planner_does_not_pad_to_three_questions(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Only one concrete branch remains.",
            "questions": [
                "Check Redis health",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# Platform Service Health Check Result",
                "",
                "## 7. Recommended Next Action",
                "Check Redis health.",
            ]),
            {
                "selected_tool": "grafana_platform_service_health",
                "user_input": "Check platform service health",
                "conversation_context": [],
            },
        )

        followup_lines = [
            line for line in answer.splitlines()
            if line.startswith("- ")
        ]
        self.assertEqual(followup_lines, ["- Check Redis health"])

    def test_followup_planner_blocks_generic_platform_health_for_emqx(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Continue EMQX runbook investigation.",
            "questions": [
                "Check platform service health",
                "Check MQTT adapter logs for any issues",
                "Check RabbitMQ queue backlog",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# EMQX Broker Health Check Result",
                "",
                "## 7. Recommended Next Action",
                "Check EMQX logs, MQTT adapter logs, broker CPU/memory, "
                "connection count, queue backlog, and core service error logs.",
            ]),
            {
                "selected_tool": "grafana_emqx_health",
                "user_input": "Review broker CPU/memory usage and connection count",
                "conversation_context": [],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertNotIn("platform service health", followups.lower())
        self.assertIn("Check MQTT adapter logs for any issues", followups)

    def test_followup_planner_treats_broker_cpu_memory_as_completed(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Continue unresolved EMQX investigation.",
            "questions": [
                "Check EMQX logs for errors or warnings",
                "Check RabbitMQ queue backlog",
                "Review broker CPU/memory usage in detail.",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# EMQX Broker Health Check Result",
                "",
                "## 7. Recommended Next Action",
                "Check EMQX logs, MQTT adapter logs, broker CPU/memory, "
                "connection count, queue backlog, and core service error logs.",
            ]),
            {
                "selected_tool": "grafana_emqx_health",
                "user_input": "Review broker CPU/memory usage and connection count",
                "conversation_context": [{
                    "role": "user",
                    "content": "Review broker CPU/memory usage and connection count",
                }],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Check MQTT adapter logs for any issues", followups)
        self.assertNotIn("broker CPU/memory usage in detail", followups)

    def test_followup_planner_keeps_uncompleted_mqtt_adapter_branch(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Continue unresolved log correlation.",
            "questions": [
                "Widen EMQX logs to the last 24 hours.",
                "Check RabbitMQ throughput.",
            ],
        })
        response.response_metadata = {}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# Grafana Log Check Result",
                "",
                "## 1. Summary",
                "Checked emqx logs without a keyword filter in the last 6 hours. Status: no_entries.",
                "",
                "## 4. Suggested Next Action",
                "Widen the time range or correlate with adjacent service logs and DB resource evidence before assigning root cause.",
            ]),
            {
                "user_input": "Check EMQX logs for errors or warnings.",
                "selected_tool": "grafana_logs",
                "tool_outputs": [],
                "conversation_context": [
                    {
                        "role": "assistant",
                        "content": (
                            "# EMQX Dropped Messages Check Result\n"
                            "Recommended Next Action\n"
                            "Check EMQX logs, MQTT adapter logs, broker CPU/memory, "
                            "connection count, queue backlog, and core service error logs."
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": "# EMQX Broker Health Check Result\nBroker status: abnormal",
                    },
                ],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Check MQTT adapter logs for any issues", followups)
        self.assertIn("Widen EMQX logs", followups)
        self.assertNotIn("RabbitMQ", followups)

    def test_queue_prompt_rejects_semantic_onem2m_tool_choice(self):
        response = MagicMock()
        response.content = json.dumps({
            "confidence": 0.9,
            "reason": "wrong domain",
            "workflows": [{
                "tool": "get_company_onem2m_device_resources",
                "params": {},
                "reason": "incorrectly treated queue as device",
                "confidence": 0.9,
            }],
        })
        response.response_metadata = {}
        model = MagicMock()
        model.invoke.return_value = response
        agent = IOAV3LangGraphN8nAgent(model=model)

        workflows, _metadata = agent.plan_workflows(
            "Check consumers for queue.onem2m.httpapi."
        )

        self.assertEqual(workflows[0]["tool"], "query_rabbitmq_queue_detail")
        self.assertEqual(
            workflows[0]["params"].get("queue_name"),
            "queue.onem2m.httpapi",
        )

    def test_queue_followup_planner_rejects_device_domain_questions(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "bad domain jump",
            "questions": [
                "What are the latest CIN records for device `requested device`?",
                "Can you provide adapter/core logs to correlate with CIN records?",
                "Check RabbitMQ throughput in namespace test",
            ],
        })
        response.response_metadata = {}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# RabbitMQ Queue Detail",
                "",
                "## 3. Suggested Next Action",
                "Check queue trend and consumer pod logs if backlog keeps increasing.",
            ]),
            {
                "user_input": "Check consumers for queue.onem2m.httpapi.",
                "selected_tool": "query_rabbitmq_queue_detail",
                "tool_outputs": [],
            },
        )

        self.assertIn("Check RabbitMQ throughput in namespace test", answer)
        self.assertNotIn("CIN", answer)
        self.assertNotIn("requested device", answer)

    def test_prompt_catalog_for_mongo_prod_keeps_runbooks_first(self):
        with patch("services.prompt_service.company_db_type", return_value="mongodb"), patch(
            "services.prompt_service.get_prompts",
            return_value=[
                {
                    "id": 99,
                    "title": "Custom",
                    "command": "custom command",
                    "category": "Custom",
                    "is_default": False,
                },
                {
                    "id": 100,
                    "title": "Old DB Default",
                    "command": "old",
                    "category": "Legacy",
                    "is_default": True,
                },
            ],
        ):
            prompts = list_prompts(user_id=1, selected_source="company")

        titles = [prompt["title"] for prompt in prompts]
        shortcuts = {prompt["title"]: prompt.get("shortcut") for prompt in prompts}
        self.assertEqual(titles[0], "Command Downlink Debug")
        self.assertEqual(shortcuts["Command Downlink Debug"], "/cmd")
        self.assertEqual(shortcuts["RabbitMQ Top Backlog"], "/rabbitmq")
        self.assertEqual(shortcuts["Infrastructure Drilldown"], "/infra")
        reconnect_prompt = next(
            prompt for prompt in prompts
            if prompt["title"] == "EMQX Reconnect Trend"
        )
        self.assertNotIn("<device_id>", reconnect_prompt["command"])
        self.assertIn("Do not require a device_id", reconnect_prompt["command"])
        self.assertIn("Ingestion Queue Health", titles)
        self.assertIn("API Health KPI", titles)
        self.assertIn("Infrastructure Drilldown", titles)
        self.assertNotIn("Company Fleet Snapshot", titles)
        self.assertNotIn("Old DB Default", titles)
        self.assertEqual(titles[-1], "Custom")
        self.assertNotIn("shortcut", prompts[-1])
        self.assertFalse(any("Scenario" in title for title in titles))

    def test_prompt_catalog_for_simulator_source_uses_simple_fallback_prompts(self):
        with patch("services.prompt_service.get_prompts", return_value=[]):
            prompts = list_prompts(user_id=1, selected_source="simulator")

        titles = [prompt["title"] for prompt in prompts]
        shortcuts = {prompt["title"]: prompt.get("shortcut") for prompt in prompts}
        categories = {prompt["category"] for prompt in prompts}

        self.assertEqual(titles[0], "Simulator Fleet Status")
        self.assertEqual(shortcuts["Simulator Fleet Status"], "/sim-fleet")
        self.assertEqual(shortcuts["Simulator Device Check"], "/sim-device")
        self.assertIn("Simulator Device Check", titles)
        self.assertIn("Simulator Fallback Smoke Test", titles)
        self.assertEqual(categories, {"Simulator"})
        self.assertNotIn("Command Downlink Debug", titles)
        self.assertNotIn("Infrastructure Drilldown", titles)

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

    def test_ioa_v3_routes_device_drilldown_followup_to_company_db_tool(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, reason = agent.classify_tool(
            "vì sao device dev-1 đang critical, phân tích evidence giúp tôi"
        )

        self.assertEqual(tool, "get_company_device_drilldown")
        self.assertEqual(params, {"device_id": "dev-1"})
        self.assertEqual(reason, "company_device_drilldown_keywords")

    def test_ioa_v3_device_drilldown_overrides_generic_semantic_alert_plan(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        workflows = [{
            "tool": "get_company_provisional_alerts",
            "params": {},
            "reason": "generic alert investigation",
            "confidence": 0.8,
            "planner": "semantic_llm",
            "tool_family": "company_db",
        }]

        planned = agent.ensure_device_drilldown_workflow(
            workflows,
            "why is device dev-1 critical? show evidence",
        )

        self.assertEqual(planned[0]["tool"], "get_company_device_drilldown")
        self.assertEqual(planned[0]["params"], {"device_id": "dev-1"})
        self.assertEqual(planned[0]["planner"], "drilldown_keyword_override")

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

    def test_ioa_v3_routes_onem2m_drilldown_followups_to_specific_tools(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        cases = [
            (
                "Thiết bị Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b có online không?",
                "query_device_online_status",
                {"device_id": "Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b"},
            ),
            (
                "Cho tôi xem AE document của thiết bị Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b",
                "query_company_onem2m_collection",
                {
                    "device_id": "Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b",
                    "collection": "AE",
                },
            ),
            (
                "Lệnh gần nhất gửi đến thiết bị Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b",
                "query_onem2m_cin_records",
                {
                    "device_id": "Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b",
                    "cin_type": "command",
                },
            ),
        ]

        for prompt, expected_tool, expected_params in cases:
            with self.subTest(prompt=prompt):
                tool, params, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)
                self.assertEqual(params, expected_params)

    def test_ioa_v3_routes_metric_drilldowns_to_specific_prometheus_tools(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        queue_tool, queue_params, _ = agent.classify_tool(
            "Chi tiết về queue iot.command.notif"
        )
        emqx_tool, emqx_params, _ = agent.classify_tool(
            "Tổng số kết nối EMQX hiện tại"
        )

        self.assertEqual(queue_tool, "query_rabbitmq_queue_detail")
        self.assertEqual(queue_params, {"queue_name": "iot.command.notif"})
        self.assertEqual(emqx_tool, "query_emqx_connection_count")
        self.assertEqual(emqx_params, {})

    def test_ioa_v3_cin_records_builder_decodes_base64_json_payload(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_cin_records_answer({
            "query_device_id": "dev-1",
            "cin_type": "command",
            "resource_summary": {
                "CIN": {
                    "command_samples": [{
                        "rn": "cin-1",
                        "pi": "cnt-command",
                        "ct": 1710000000000,
                        "con": "eyJjb21tYW5kIjogInJlc3RhcnQifQ==",
                    }],
                    "telemetry_samples": [],
                    "samples": [],
                }
            },
        })

        self.assertIn('"command": "restart"', answer)
        self.assertIn("2024-03-09T16:00:00Z", answer)
        self.assertIn("**Record 1: COMMAND CIN**", answer)
        self.assertNotIn("### 1. COMMAND CIN", answer)
        self.assertIn("## Follow-up Questions", answer)

    def test_ioa_v3_device_online_builder_reads_ae_poast_and_poa(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_device_online_answer({
            "query_device_id": "dev-1",
            "resource_summary": {
                "AE": {
                    "samples": [{
                        "rn": "ae-dev-1",
                        "aei": "Cdev1",
                        "poast": 1,
                        "poa": ["mqtt://broker/dev-1"],
                        "lt": 1710000000000,
                    }]
                },
                "CIN": {"present": True},
            },
        })

        self.assertIn("**ONLINE**", answer)
        self.assertIn("mqtt://broker/dev-1", answer)
        self.assertIn("2024-03-09T16:00:00Z", answer)

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

    def test_ioa_v3_full_command_debug_prompt_routes_to_command_flow(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, _ = agent.classify_tool(
            "Debug why device S5bacab3c-a8c7-46fa-8d77-a86c4f5c62a6 did not "
            "receive a command. Treat S5bacab3c-a8c7-46fa-8d77-a86c4f5c62a6 "
            "as the only required operator input. Derive AE ID and "
            "request/correlation IDs from MongoDB resources, URI mapper, latest "
            "command CIN records, and adapter/core logs. Check iot-http-api and "
            "iot-mqtt-client-adapter logs, core logs, IDENTITY, AE, cnt_command, "
            "SUBSCRIPTION, URI_MAPPER, and latest command CIN evidence. "
            "Summarize the most likely failure point, supporting evidence, "
            "evidence gaps, and the next action. Time range: last 6 hours."
        )

        self.assertEqual(tool, "get_company_onem2m_command_flow")
        self.assertEqual(
            params["device_id"],
            "S5bacab3c-a8c7-46fa-8d77-a86c4f5c62a6",
        )

    def test_ioa_v3_resource_check_prompt_does_not_route_to_online_status(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        prompt = (
            "Check whether device S5bacab3c-a8c7-46fa-8d77-a86c4f5c62a6 is "
            "registered on the platform and whether its required OneM2M "
            "resources exist. Treat S5bacab3c-a8c7-46fa-8d77-a86c4f5c62a6 as "
            "the only required operator input. Derive AE ID and "
            "request/correlation IDs from MongoDB resources and logs when "
            "needed. Check iot-http-api and iot-mqtt-client-adapter logs, then "
            "verify IDENTITY, AE, CNT, CIN, SUBSCRIPTION, and URI_MAPPER "
            "evidence. List exactly which resources exist, which are missing, "
            "what evidence supports each status, and the next action. "
            "Time range: last 6 hours."
        )

        tool, params, _ = agent.classify_tool(prompt)
        workflows = agent.ensure_runbook_required_workflows([], prompt)

        self.assertEqual(tool, "get_company_onem2m_device_resources")
        self.assertEqual(
            params["device_id"],
            "S5bacab3c-a8c7-46fa-8d77-a86c4f5c62a6",
        )
        self.assertEqual(
            [workflow["tool"] for workflow in workflows],
            ["get_company_onem2m_device_resources"],
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

        self.assertIn("| `IDENTITY` | **Missing** |", answer)
        self.assertIn("| `AE` | Present |", answer)
        self.assertIn("| `CIN` | **Missing** |", answer)
        self.assertIn("| `URI_MAPPER` | **Missing** |", answer)
        self.assertIn("incomplete OneM2M registration", answer)

    def test_onem2m_resource_evidence_adds_soft_wrap_points(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        evidence = agent.onem2m_resource_evidence_summary({
            "samples": [{
                "_id": "in-name/S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f",
            }]
        })

        self.assertIn("\u200b", evidence)
        self.assertIn("in-\u200bname/\u200bS3e1c21c3-\u200b7aad", evidence)

    def test_onem2m_command_answer_uses_failure_point_not_root_cause(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_onem2m_flow_answer(
            {
                "query_device_id": "S123",
                "command_record_count": 0,
                "devices": [{
                    "status": "resource_matches_found",
                    "telemetry_record_count": 0,
                }],
                "input_evidence": {
                    "derived_identifiers": {
                        "ae_id_candidates": ["AE-S123"],
                        "request_id_candidates": [],
                    },
                },
                "resource_summary": {
                    "IDENTITY": {"present": False, "matched_count": 0},
                    "AE": {"present": True, "matched_count": 1},
                    "CNT": {
                        "present": True,
                        "matched_count": 2,
                        "command_count": 1,
                        "telemetry_count": 1,
                    },
                    "CIN": {
                        "present": False,
                        "matched_count": 0,
                        "command_count": 0,
                        "telemetry_count": 0,
                    },
                    "SUBSCRIPTION": {"present": True, "matched_count": 1},
                    "URI_MAPPER": {"present": False, "matched_count": 0},
                },
                "flow_checks": {
                    "required_input_complete": True,
                    "identity_present": False,
                    "ae_present": True,
                    "command_container_present": True,
                    "subscription_present": True,
                    "uri_mapper_present": False,
                    "latest_command_cin_present": False,
                },
            },
            "get_company_onem2m_command_flow",
            [{
                "source": "n8n_grafana_gateway",
                "tool": "grafana_logs",
                "http_call": {"method": "GET", "path": "/grafana/logs"},
                "result": {"level": "error|warn"},
            }],
        )

        self.assertIn("Likely Failure Point", answer)
        self.assertIn("Evidence Gaps", answer)
        self.assertIn("grafana_logs: executed GET /grafana/logs", answer)
        self.assertIn("not a proven underlying code/config root cause", answer)
        self.assertNotIn("most likely root cause", answer.lower())

    def test_onem2m_telemetry_answer_includes_notify_style_next_step(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_onem2m_flow_answer(
            {
                "query_device_id": "S123",
                "devices": [{
                    "status": "resource_matches_found",
                    "telemetry_record_count": 0,
                }],
                "resource_summary": {
                    "IDENTITY": {"present": False, "matched_count": 0},
                    "AE": {"present": True, "matched_count": 1},
                    "CNT": {
                        "present": True,
                        "matched_count": 2,
                        "telemetry_count": 1,
                    },
                    "CIN": {
                        "present": False,
                        "matched_count": 0,
                        "telemetry_count": 0,
                    },
                    "SUBSCRIPTION": {"present": True, "matched_count": 1},
                    "URI_MAPPER": {"present": False, "matched_count": 0},
                },
                "flow_checks": {
                    "required_input_complete": True,
                    "identity_present": False,
                    "ae_present": True,
                    "telemetry_container_present": True,
                    "backend_subscription_present": True,
                    "latest_telemetry_cin_present": False,
                },
                "next_diagnostic_step": (
                    "Correlate latest telemetry CIN with backend SUBSCRIPTION "
                    "notify logs, adapter receive logs, and backend delivery evidence."
                ),
            },
            "get_company_onem2m_telemetry_flow",
            [],
        )

        self.assertIn("| cnt_telemetry container | Present |", answer)
        self.assertIn("| Latest telemetry CIN | Missing |", answer)
        self.assertIn("backend SUBSCRIPTION notify logs", answer)
        self.assertIn("No Grafana/Loki workflow evidence", answer)

    def test_onem2m_telemetry_answer_flags_offline_status_evidence(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_onem2m_flow_answer(
            {
                "query_device_id": "S3e1",
                "devices": [{
                    "status": "resource_matches_found",
                    "telemetry_record_count": 2,
                }],
                "resource_summary": {
                    "IDENTITY": {"present": True, "matched_count": 1},
                    "AE": {
                        "present": True,
                        "matched_count": 1,
                        "samples": [{
                            "rn": "S3e1",
                            "aei": "S3e1",
                            "poast": [{
                                "pointOfAccess": "mqtt://S3e1",
                                "status": 0,
                            }],
                        }],
                    },
                    "CNT": {
                        "present": True,
                        "matched_count": 2,
                        "telemetry_count": 1,
                    },
                    "CIN": {
                        "present": True,
                        "matched_count": 2,
                        "telemetry_count": 2,
                        "telemetry_samples": [
                            {"con": "{\"status\": \"disconnected\"}"},
                            {"con": "{\"temp\": 28.7}"},
                        ],
                    },
                    "SUBSCRIPTION": {"present": True, "matched_count": 1},
                    "URI_MAPPER": {"present": True, "matched_count": 1},
                },
                "flow_checks": {
                    "required_input_complete": True,
                    "identity_present": True,
                    "ae_present": True,
                    "telemetry_container_present": True,
                    "backend_subscription_present": True,
                    "latest_telemetry_cin_present": True,
                },
            },
            "get_company_onem2m_telemetry_flow",
            [],
        )

        self.assertIn("required telemetry uplink DB resources", answer)
        self.assertIn("AE point-of-access status is OFFLINE", answer)
        self.assertIn("latest telemetry CIN reports status `disconnected`", answer)
        self.assertIn("not missing OneM2M resources", answer)
        self.assertIn("Check notify logs for device S3e1", answer)
        self.assertNotIn("Debug telemetry uplink for device S3e1", answer)

    def test_onem2m_cin_followups_progress_to_logs_and_ae_context(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_cin_records_answer({
            "query_device_id": "S3e1",
            "cin_type": "telemetry",
            "resource_summary": {
                "AE": {"present": True, "matched_count": 1},
                "CIN": {
                    "present": True,
                    "telemetry_samples": [
                        {"con": "{\"status\": \"disconnected\"}"},
                        {"con": "{\"status\": \"connected\"}"},
                    ],
                },
            },
        })

        self.assertIn("Is device S3e1 online?", answer)
        self.assertIn("Check notify logs for device S3e1", answer)
        self.assertIn("Show the AE document for device S3e1", answer)
        self.assertIn("## 3. Suggested Next Action", answer)
        self.assertIn("adapter/core logs", answer)
        self.assertNotIn("Debug telemetry uplink for device S3e1", answer)

    def test_onem2m_cin_followups_survive_false_planner_response(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": False,
            "reason": "Planner incorrectly stopped after evidence view.",
            "questions": [],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer = agent.build_cin_records_answer({
            "query_device_id": "S3e1",
            "cin_type": "telemetry",
            "resource_summary": {
                "AE": {"present": True, "matched_count": 1},
                "CIN": {
                    "present": True,
                    "telemetry_samples": [
                        {"con": "{\"status\": \"disconnected\"}"},
                    ],
                },
            },
        })

        planned, _ = agent.apply_followup_planner(
            answer,
            {
                "selected_tool": "query_onem2m_cin_records",
                "user_input": "Correlate latest CIN records with adapter/core logs.",
                "conversation_context": [],
            },
        )

        self.assertIn("## 3. Suggested Next Action", planned)
        self.assertIn("## Follow-up Questions", planned)
        self.assertIn("Is device S3e1 online?", planned)
        self.assertNotIn("<queue_id>", planned)

    def test_onem2m_followup_planner_rejects_queue_placeholders(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "bad mixed-domain suggestions",
            "questions": [
                "Show CNT containers for device S3e1",
                "Show details for queue <queue_id>",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# OneM2M CIN Records",
                "",
                "## 1. Summary",
                "Found 2 bounded CIN sample(s) for device S3e1.",
            ]),
            {
                "selected_tool": "query_onem2m_cin_records",
                "user_input": "Correlate latest CIN records with adapter/core logs.",
                "conversation_context": [],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Show CNT containers for device S3e1", followups)
        self.assertNotIn("<queue_id>", followups)
        self.assertNotIn("queue", followups.lower())

    def test_onem2m_suggestion_section_filters_queue_domain(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        section = agent.suggestion_section(
            [
                "Show CNT containers for device S3e1",
                "Show details for queue <queue_id>",
            ],
            selected_tool="query_onem2m_cin_records",
        )

        text = "\n".join(section)
        self.assertIn("Show CNT containers for device S3e1", text)
        self.assertNotIn("<queue_id>", text)

    def test_onem2m_suggestion_section_filters_generic_log_followups(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        section = agent.suggestion_section(
            [
                "Query logs for device S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f",
                "Check logs for device S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f",
                "Check iot-http-api logs for device S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f in the last 3 hours",
                "Check iot-mqtt-client-adapter logs for device S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f in the last 3 hours",
            ],
            selected_tool="get_company_onem2m_command_flow",
        )

        text = "\n".join(section)
        self.assertNotIn("Query logs for device", text)
        self.assertNotIn("Check logs for device", text)
        self.assertIn("iot-http-api logs", text)
        self.assertIn("iot-mqtt-client-adapter logs", text)

    def test_command_cin_answer_suggests_concrete_log_sources(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        answer = agent.build_cin_records_answer({
            "answer_language": "en",
            "query_device_id": device_id,
            "cin_type": "command",
            "current_user_input": f"CIN records for device {device_id}",
            "resource_summary": {
                "CIN": {
                    "command_samples": [{
                        "rn": "cin_28d0d7c0d94d",
                        "pi": "cnt-command",
                        "ct": 1783473109665,
                        "con": "{\"commandId\":\"ota_2_0_0\"}",
                    }],
                },
            },
        })

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Check iot-http-api logs for device", followups)
        self.assertIn("Check iot-mqtt-client-adapter logs for device", followups)
        self.assertNotIn("Query logs for device", followups)

    def test_onem2m_collection_followups_do_not_repeat_current_question(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_onem2m_collection_answer({
            "query_device_id": "S3e1",
            "query_collection": "SUBSCRIPTION",
            "current_user_input": (
                "Show SUBSCRIPTION documents for device S3e1"
            ),
            "resource_summary": {
                "AE": {"present": True, "samples": [{"rn": "ae-S3e1"}]},
                "CIN": {"present": True, "samples": [{"rn": "cin-S3e1"}]},
                "SUBSCRIPTION": {
                    "present": True,
                    "samples": [{"rn": "sub_S3e1_command"}],
                },
            },
        })

        self.assertIn("## Follow-up Questions", answer)
        self.assertIn("Is device S3e1 online?", answer)
        self.assertIn("CIN records for device S3e1", answer)
        self.assertNotIn(
            "- Show SUBSCRIPTION documents for device S3e1",
            answer,
        )

    def test_grafana_log_followup_answer_keeps_drilldown_suggestions(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_grafana_logs_answer({
            "answer_language": "en",
            "current_user_input": (
                "Check notify logs for device S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f in the last 3 hours"
            ),
            "request": {
                "service_name": "notify",
                "contains": "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f",
                "hours_back": 3,
            },
            "logs": [],
        })

        self.assertIn("## Follow-up Questions", answer)
        self.assertIn(
            "Check iot-mqtt-client-adapter logs for device "
            "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f",
            answer,
        )
        self.assertIn(
            "Show the AE document for device "
            "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f",
            answer,
        )
        self.assertIn("Checked notify logs filtered by S3e1c21c3", answer)
        self.assertIn("- Service: notify", answer)
        self.assertNotIn("`notify`", answer)
        self.assertNotIn(
            "- Check notify logs for device "
            "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f in the last 3 hours",
            answer,
        )

    def test_emqx_log_answer_keeps_reconnect_drilldown_on_mqtt_path(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_grafana_logs_answer({
            "answer_language": "en",
            "current_user_input": "Check EMQX logs for errors or warnings",
            "request": {
                "service_name": "emqx",
                "contains": None,
                "hours_back": 6,
            },
            "logs": [],
        })

        self.assertIn("Check MQTT adapter logs for reconnect evidence", answer)
        self.assertIn("Widen EMQX logs", answer)
        self.assertNotIn("Check RabbitMQ throughput", answer)

    def test_grafana_log_answer_displays_decoded_time_range(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_grafana_logs_answer({
            "answer_language": "en",
            "current_user_input": "Check EMQX logs in the last 6 hours",
            "request": {
                "service_name": "emqx",
                "contains": None,
                "hours_back": 6,
                "start": 1784620000,
                "end": 1784641600,
            },
            "logs": [],
        })

        self.assertIn("Time range: 1784620000 → 1784641600 (last 6 hours)", answer)

    def test_grafana_log_answer_handles_missing_target_without_fake_service(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_grafana_logs_answer({
            "answer_language": "en",
            "current_user_input": "Review queue-processing service logs for errors.",
            "level": "needs_target",
            "request": {
                "service_name": None,
                "contains": None,
                "hours_back": 6,
            },
            "logs": [],
        })

        self.assertIn("Status: **needs_target**", answer)
        self.assertIn("No Loki query was executed", answer)
        self.assertIn("Check EMQX logs", answer)
        self.assertIn("Check MQTT adapter logs", answer)
        self.assertIn("Check RabbitMQ queue backlog", answer)
        self.assertNotIn("requested service", answer)
        self.assertNotIn("for ``", answer)
        self.assertNotIn("<service>", answer)

    def test_reconnect_error_logs_route_to_mqtt_adapter(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, _ = agent.classify_tool(
            "Inspect error logs before reconnect events"
        )

        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params.get("service"), "iot-mqtt-client-adapter")

    def test_mqtt_adapter_reconnect_log_followup_routes_to_loki(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, _ = agent.classify_tool(
            "Check MQTT adapter logs for reconnect evidence"
        )

        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params.get("service"), "iot-mqtt-client-adapter")

    def test_emqx_log_no_entries_suggests_concrete_widen_and_mqtt_adjacent(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Planner returned a generic branch.",
            "questions": [
                "Check RabbitMQ throughput",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# Grafana Log Check Result",
                "",
                "## 1. Summary",
                "Checked emqx logs filtered by reconnect in the last 6 hours. Status: no_entries.",
                "",
                "## 4. Suggested Next Action",
                "- Widen the time range or correlate with adjacent service logs and DB resource evidence before assigning root cause.",
            ]),
            {
                "selected_tool": "grafana_logs",
                "user_input": "Check EMQX logs for errors or warnings",
                "conversation_context": [{
                    "role": "assistant",
                    "content": (
                        "# EMQX Connect/Disconnect Check Result\n"
                        "## 7. Recommended Next Action\n"
                        "Check MQTT adapter logs for reconnect evidence, "
                        "check EMQX logs for broker-side errors, and review EMQX broker health."
                    ),
                }],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Widen EMQX logs to last 24 hours", followups)
        self.assertIn("Check MQTT adapter logs for reconnect evidence", followups)
        self.assertNotIn("RabbitMQ throughput", followups)

    def test_queue_log_followups_use_queue_as_loki_keyword_not_service_target(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        for prompt, expected_hours in (
            ("Review related error logs for queue queue.api.subNnotif", None),
            ("Widen queue.api.subNnotif logs to last 24 hours", 24),
        ):
            with self.subTest(prompt=prompt):
                tool, params, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, "grafana_logs")
                self.assertNotIn("service", params)
                self.assertEqual(params.get("contains"), "queue.api.subNnotif")
                if expected_hours:
                    self.assertEqual(params.get("hours_back"), expected_hours)

    def test_log_answer_with_keyword_target_does_not_claim_missing_service(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        answer = agent.build_grafana_logs_answer({
            "answer_language": "en",
            "current_user_input": "Widen queue.api.subNnotif logs to last 24 hours",
            "request": {
                "service_name": None,
                "contains": "queue.api.subNnotif",
                "hours_back": 24,
            },
            "logs": [],
        })

        self.assertIn("Checked logs filtered by queue.api.subNnotif", answer)
        self.assertIn("Status: **no_entries**", answer)
        self.assertNotIn("not-yet-specified service", answer)
        self.assertNotIn("needs_target", answer)

    def test_log_followup_widen_advances_from_answer_time_window(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Planner repeated the old widen window.",
            "questions": [
                "Widen EMQX logs to last 24 hours",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        planned, _ = agent.apply_followup_planner(
            "\n".join([
                "# Grafana Log Check Result",
                "",
                "## 1. Summary",
                "Checked emqx logs without a keyword filter in the last 24 hours. Status: no_entries.",
                "",
                "## 4. Suggested Next Action",
                "- Widen the time range or correlate with adjacent service logs and DB resource evidence before assigning root cause.",
            ]),
            {
                "selected_tool": "grafana_logs",
                "user_input": "Check EMQX logs for broker-side errors",
                "conversation_context": [],
            },
        )

        followups = planned.split("## Follow-up Questions")[-1]
        self.assertIn("Widen EMQX logs to last 48 hours", followups)
        self.assertNotIn("Widen EMQX logs to last 24 hours", followups)

    def test_drilldown_question_routing_table_tools_are_covered(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"
        cases = [
            (f"Kiểm tra thiết bị {device_id} có lên hệ thống chưa", "get_company_onem2m_device_resources"),
            (f"Thiết bị {device_id} có online không?", "query_device_online_status"),
            (f"Cho tôi xem AE document của thiết bị {device_id}", "query_company_onem2m_collection"),
            (f"Show me all CNT containers for device {device_id}", "query_company_onem2m_collection"),
            (f"Lệnh gần nhất gửi đến thiết bị {device_id}", "query_onem2m_cin_records"),
            (f"Latest telemetry from device {device_id}", "query_onem2m_cin_records"),
            (f"Debug command downlink for device {device_id}", "get_company_onem2m_command_flow"),
            (f"Debug telemetry uplink for device {device_id}", "get_company_onem2m_telemetry_flow"),
            ("Top 10 RabbitMQ queues", "grafana_queue_backlog"),
            ("Chi tiết về queue queue.onem2m.datamgmt", "query_rabbitmq_queue_detail"),
            ("Check RabbitMQ queue trend", "grafana_queue_trend"),
            ("EMQX dropped messages", "grafana_emqx_dropped_trend"),
            ("Current EMQX connection count", "query_emqx_connection_count"),
            ("EMQX connect/disconnect rate", "grafana_emqx_connection_trend"),
            ("K8s resource usage", "grafana_k8s_resources"),
            ("Check HTTP API success rate", "grafana_http_health"),
            ("RabbitMQ throughput", "grafana_throughput"),
            ("Check MQTT adapter logs for reconnect evidence", "grafana_logs"),
        ]

        for prompt, expected_tool in cases:
            with self.subTest(prompt=prompt):
                tool, _, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)

    def test_onem2m_followups_keep_recent_device_context(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"
        context = [{
            "role": "assistant",
            "content": (
                "# OneM2M Device Resource Check Result\n"
                f"Device ID: {device_id}\n"
                "## 7. Suggested Next Action\n"
                "Continue with the command or telemetry flow workflow and correlate latest CIN records."
            ),
        }]
        cases = [
            (
                "Continue with the command or telemetry flow workflow.",
                "get_company_onem2m_command_flow",
            ),
            (
                "Correlate latest command CIN with adapter logs for device requested device.",
                "get_company_onem2m_command_flow",
            ),
            (
                "Investigate AE ID variants for device requested.",
                "get_company_onem2m_device_resources",
            ),
            (
                "Re-run the registration/provisioning trace for the missing resources.",
                "get_company_onem2m_device_resources",
            ),
        ]

        for prompt, expected_tool in cases:
            with self.subTest(prompt=prompt):
                resolved = agent.resolve_contextual_user_input(prompt, context)
                tool, params, _ = agent.classify_tool(resolved)
                self.assertEqual(tool, expected_tool)
                self.assertEqual(params.get("device_id"), device_id)
                self.assertNotIn("requested", str(params))

    def test_onem2m_delivery_and_status_followups_route_to_bounded_tools(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b"
        cases = [
            (
                f"Verify the operational status of AE for device {device_id}.",
                "query_device_online_status",
            ),
            (
                f"Verify AE online status for device {device_id}.",
                "query_device_online_status",
            ),
            (
                f"Search for backend delivery evidence related to device {device_id}.",
                "get_company_onem2m_telemetry_flow",
            ),
            (
                device_id,
                "get_company_onem2m_device_resources",
            ),
        ]

        for prompt, expected_tool in cases:
            with self.subTest(prompt=prompt):
                tool, params, _ = agent.classify_tool(prompt)
                self.assertEqual(tool, expected_tool)
                self.assertEqual(params.get("device_id"), device_id)

    def test_ae_operational_status_followup_keeps_context_device(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        resolved = agent.resolve_contextual_user_input(
            "Check the operational status of AE point-of-access for any updates.",
            [{
                "role": "assistant",
                "content": (
                    "# OneM2M Command Downlink Flow Check Result\n"
                    f"Device ID: {device_id}\n"
                    "AE point-of-access status is OFFLINE."
                ),
            }],
        )

        self.assertIn(f"device {device_id}", resolved)
        tool, params, _ = agent.classify_tool(resolved)
        self.assertEqual(tool, "query_device_online_status")
        self.assertEqual(params.get("device_id"), device_id)

    def test_command_cin_timestamp_log_followup_routes_to_loki(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        for prompt, expected_service in (
            (
                "Correlate the latest command CIN timestamp with iot-http-api/core logs.",
                "iot-http-api",
            ),
            (
                "Correlate the latest command CIN with iot-http-api logs.",
                "iot-http-api",
            ),
            (
                "Correlate the latest command CIN timestamp with iot-mqtt-client-adapter send logs.",
                "iot-mqtt-client-adapter",
            ),
        ):
            with self.subTest(prompt=prompt):
                resolved = agent.resolve_contextual_user_input(
                    prompt,
                    [{
                        "role": "assistant",
                        "content": (
                            "# OneM2M CIN Records\n"
                            f"Found 3 bounded CIN sample(s) for device {device_id}.\n"
                            "Record 1: COMMAND CIN\n"
                            "rn: cin_28d0d7c0d94d"
                        ),
                    }],
                )

                self.assertIn(f"device {device_id}", resolved)
                tool, params, _ = agent.classify_tool(resolved)
                self.assertEqual(tool, "grafana_logs")
                self.assertEqual(params.get("service"), expected_service)
                self.assertEqual(params.get("contains"), device_id)
                self.assertNotIn("collection", params)

    def test_ae_point_of_access_core_logs_route_to_loki(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        resolved = agent.resolve_contextual_user_input(
            "Check AE point-of-access status in core logs.",
            [{
                "role": "assistant",
                "content": (
                    "# OneM2M Command Downlink Flow Check Result\n"
                    f"Device ID: {device_id}\n"
                    "AE point-of-access status is OFFLINE."
                ),
            }],
        )

        self.assertIn(f"device {device_id}", resolved)
        tool, params, _ = agent.classify_tool(resolved)
        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params.get("contains"), device_id)
        self.assertNotIn("collection", params)

    def test_ae_point_of_access_without_logs_routes_to_online_status(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        tool, params, _ = agent.classify_tool(
            f"Check AE point-of-access for device {device_id}"
        )

        self.assertEqual(tool, "query_device_online_status")
        self.assertEqual(params.get("device_id"), device_id)

    def test_recent_mqtt_logs_mean_mqtt_adapter_logs(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        tool, params, _ = agent.classify_tool(
            f"Review recent MQTT logs for device {device_id}"
        )

        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params.get("service"), "iot-mqtt-client-adapter")
        self.assertEqual(params.get("contains"), device_id)

    def test_onem2m_timestamp_log_followups_keep_device_from_cin_answer(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"
        context = [{
            "role": "assistant",
            "content": (
                "# OneM2M CIN Records\n"
                "## 2. Records\n"
                "Record 1: TELEMETRY CIN\n"
                "decoded con:\n"
                "{ "
                f'"deviceId": "{device_id}", '
                f'"deviceName": "{device_id}", '
                '"status": "disconnected"'
                " }\n"
                "## 3. Suggested Next Action\n"
                "Correlate these CIN timestamps and decoded statuses with "
                "adapter/core logs, notify delivery logs, and AE online status "
                "before assigning root cause."
            ),
        }]
        cases = [
            "Check notify delivery logs for the relevant timestamps.",
            "Check iot-mqtt-client-adapter receive logs for device requested device.",
        ]

        for prompt in cases:
            with self.subTest(prompt=prompt):
                resolved = agent.resolve_contextual_user_input(prompt, context)
                self.assertIn(f"device {device_id}", resolved)
                tool, params, _ = agent.classify_tool(resolved)
                self.assertEqual(tool, "get_company_onem2m_telemetry_flow")
                self.assertEqual(params.get("device_id"), device_id)
                self.assertNotIn("requested", str(params))

    def test_device_configuration_change_followup_uses_bounded_onem2m_collection(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        tool, params, reason = agent.classify_tool(
            f"Investigate any recent changes to the configuration of device {device_id}"
        )

        self.assertEqual(tool, "query_company_onem2m_collection")
        self.assertEqual(params["device_id"], device_id)
        self.assertEqual(params["collection"], "AE")
        self.assertEqual(reason, "company_onem2m_device_config_keywords")

    def test_command_flow_next_action_does_not_claim_missing_resource_checks(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        answer = agent.build_onem2m_flow_answer(
            {
                "answer_language": "en",
                "query_device_id": "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f",
                "flow_name": "command",
                "device_status": "resource_matches_found",
                "resource_summary": {
                    "IDENTITY": {"status": "Present", "matched_count": 1},
                    "AE": {"status": "Present", "matched_count": 1},
                    "CNT": {"status": "Present", "matched_count": 1},
                    "CIN": {"status": "Present", "matched_count": 1},
                    "SUBSCRIPTION": {"status": "Present", "matched_count": 1},
                    "URI_MAPPER": {"status": "Present", "matched_count": 1},
                },
                "flow_checks": {
                    "required_input_complete": True,
                    "identity_present": True,
                    "ae_present": True,
                    "command_container_present": True,
                    "subscription_present": True,
                    "uri_mapper_present": True,
                    "latest_command_cin_present": True,
                },
                "log_evidence": [],
            },
            "get_company_onem2m_command_flow",
            [],
        )

        self.assertIn("latest command CIN", answer)
        self.assertIn("iot-mqtt-client-adapter send logs", answer)
        self.assertNotIn("missing resource checks", answer)

    def test_onem2m_related_log_followups_route_to_loki_not_resource_check(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        tool, params, _ = agent.classify_tool(
            f"Correlate the latest command CIN with adapter logs for device {device_id}."
        )
        self.assertEqual(tool, "get_company_onem2m_command_flow")
        self.assertEqual(params.get("device_id"), device_id)

        tool, params, _ = agent.classify_tool(
            "Check wider time range for logs related to AE ID candidates: "
            "N1deb6685-493c-431f-8be0-577f61ab9368, "
            "N946df3c8-5c7f-4f62-a00c-0de297f13956, "
            f"{device_id}."
        )
        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params.get("contains"), "N1deb6685-493c-431f-8be0-577f61ab9368")

    def test_reconnect_log_followup_prunes_unrelated_rabbitmq(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": True,
            "reason": "Continue reconnect drilldown.",
            "questions": [
                "Check RabbitMQ throughput",
                "Check MQTT adapter logs for reconnect evidence",
            ],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer, _ = agent.apply_followup_planner(
            "\n".join([
                "# Grafana Log Check Result",
                "",
                "## 1. Summary",
                "Checked emqx logs without a keyword filter in the last 6 hours. Status: no_entries.",
                "",
                "## 4. Suggested Next Action",
                "- Widen the time range or correlate with adjacent service logs.",
            ]),
            {
                "selected_tool": "grafana_logs",
                "user_input": "Check EMQX logs for errors or warnings",
                "conversation_context": [{
                    "role": "assistant",
                    "content": (
                        "# EMQX Connect/Disconnect Check Result\n"
                        "Recommended Next Action\n"
                        "Check MQTT adapter logs for reconnect evidence and check EMQX logs."
                    ),
                }],
            },
        )

        followups = answer.split("## Follow-up Questions")[-1]
        self.assertIn("Check MQTT adapter logs for reconnect evidence", followups)
        self.assertNotIn("RabbitMQ throughput", followups)

    def test_log_next_action_fallback_survives_false_planner_response(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        response = MagicMock()
        response.content = json.dumps({
            "needs_followup": False,
            "reason": "Planner incorrectly stopped despite open log next action.",
            "questions": [],
        })
        response.response_metadata = {"token_usage": {}}
        agent.model = MagicMock()
        agent.model.invoke.return_value = response

        answer = agent.build_grafana_logs_answer({
            "answer_language": "en",
            "current_user_input": "Check EMQX logs for errors or warnings",
            "request": {
                "service_name": "emqx",
                "contains": None,
                "hours_back": 6,
            },
            "logs": [],
        })

        planned, _ = agent.apply_followup_planner(
            answer,
            {
                "selected_tool": "grafana_logs",
                "user_input": "Check EMQX logs for errors or warnings",
                "conversation_context": [],
            },
        )

        followups = planned.split("## Follow-up Questions")[-1]
        self.assertIn("Check MQTT adapter logs for reconnect evidence", followups)
        self.assertIn("Widen EMQX logs", followups)

    def test_onem2m_telemetry_answer_marks_failed_log_source_as_gap(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_onem2m_flow_answer(
            {
                "query_device_id": "S3e1",
                "devices": [{
                    "status": "resource_matches_found",
                    "telemetry_record_count": 2,
                }],
                "resource_summary": {
                    "IDENTITY": {"present": True, "matched_count": 1},
                    "AE": {"present": True, "matched_count": 1},
                    "CNT": {
                        "present": True,
                        "matched_count": 2,
                        "telemetry_count": 1,
                    },
                    "CIN": {
                        "present": True,
                        "matched_count": 2,
                        "telemetry_count": 2,
                    },
                    "SUBSCRIPTION": {"present": True, "matched_count": 1},
                    "URI_MAPPER": {"present": True, "matched_count": 1},
                },
                "flow_checks": {
                    "required_input_complete": True,
                    "identity_present": True,
                    "ae_present": True,
                    "telemetry_container_present": True,
                    "backend_subscription_present": True,
                    "latest_telemetry_cin_present": True,
                },
            },
            "get_company_onem2m_telemetry_flow",
            [{
                "source": "mcp_server",
                "tool": "grafana_logs",
                "http_call": {
                    "params": {
                        "service_name": "notify",
                        "contains": "S3e1",
                        "hours_back": 6,
                    }
                },
                "result": {
                    "error": "MCP tool call failed before tool result",
                },
            }],
        )

        self.assertIn("service=notify", answer)
        self.assertIn("unavailable=MCP tool call failed", answer)
        self.assertIn("One or more log sources were unavailable", answer)
        self.assertIn("notify (MCP tool call failed", answer)

    def test_onem2m_flow_followups_follow_next_action_not_static_checklist(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        answer = agent.build_onem2m_flow_answer(
            {
                "query_device_id": "S3e1",
                "devices": [{
                    "status": "resource_matches_found",
                    "telemetry_record_count": 2,
                }],
                "next_diagnostic_step": (
                    "Correlate latest telemetry CIN with "
                    "iot-mqtt-client-adapter receive logs and notify delivery logs."
                ),
                "resource_summary": {
                    "IDENTITY": {"present": True, "matched_count": 1},
                    "AE": {"present": True, "matched_count": 1},
                    "CNT": {
                        "present": True,
                        "matched_count": 2,
                        "telemetry_count": 1,
                    },
                    "CIN": {
                        "present": True,
                        "matched_count": 2,
                        "telemetry_count": 2,
                    },
                    "SUBSCRIPTION": {"present": True, "matched_count": 1},
                    "URI_MAPPER": {"present": True, "matched_count": 1},
                },
                "flow_checks": {
                    "required_input_complete": True,
                    "identity_present": True,
                    "ae_present": True,
                    "telemetry_container_present": True,
                    "backend_subscription_present": True,
                    "latest_telemetry_cin_present": True,
                },
            },
            "get_company_onem2m_telemetry_flow",
            [],
        )

        self.assertIn("Check notify logs for device S3e1", answer)
        self.assertIn("Check iot-mqtt-client-adapter logs for device S3e1", answer)
        self.assertIn("Show latest telemetry from device S3e1", answer)
        self.assertNotIn("Show SUBSCRIPTION documents for device S3e1", answer)

    def test_loki_query_uses_single_full_window_call_when_successful(self):
        with (
            patch.object(
                mcp_observability_service,
                "_find_datasource_uid",
                return_value="loki_uid",
            ),
            patch.object(
                mcp_observability_service,
                "_loki_query_chunk",
                return_value=[],
            ) as query_chunk,
        ):
            evidence = mcp_observability_service.query_loki_logs_via_mcp(
                service_name="notify",
                contains="S3e1",
                hours_back=6,
            )

        self.assertEqual(query_chunk.call_count, 1)
        self.assertEqual(evidence["request"]["hours_back"], 6)
        self.assertEqual(evidence["result"], [])

    def test_log_followup_extracts_service_device_and_time_window(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, _ = agent.classify_tool(
            "Check notify logs for device "
            "Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b in the last 3 hours"
        )

        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params["service"], "notify")
        self.assertEqual(
            params["contains"],
            "Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b",
        )
        self.assertEqual(params["hours_back"], 3)

    def test_log_followup_normalizes_mqtt_adapter_alias(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        for prompt in (
            "Check MQTT adapter logs for any issues.",
            "Widen the time range for the `mqtt_adapter` logs and check again.",
        ):
            tool, params, _ = agent.classify_tool(prompt)
            self.assertEqual(tool, "grafana_logs")
            self.assertEqual(params["service"], "iot-mqtt-client-adapter")

    def test_vague_log_followup_resolves_previous_log_target(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        resolved = agent.resolve_contextual_user_input(
            "Widen the time range for the log check.",
            [
                {
                    "role": "user",
                    "content": "Check MQTT adapter logs for any issues.",
                },
                {
                    "role": "assistant",
                    "content": (
                        "Grafana Log Check Result\n"
                        "Checked iot-mqtt-client-adapter logs without a keyword "
                        "filter in the last 6 hours.\n"
                        "Service: iot-mqtt-client-adapter\n"
                        "Contains: not specified"
                    ),
                },
            ],
        )

        self.assertIn("service iot-mqtt-client-adapter", resolved)
        self.assertIn("last 24 hours", resolved)
        tool, params, _ = agent.classify_tool(resolved)
        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params["service"], "iot-mqtt-client-adapter")
        self.assertEqual(params["hours_back"], 24)

    def test_concrete_widen_log_followup_keeps_previous_keyword_filter(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        resolved = agent.resolve_contextual_user_input(
            "Widen MQTT adapter logs to last 24 hours",
            [
                {
                    "role": "assistant",
                    "content": (
                        "# Grafana Log Check Result\n"
                        "Checked iot-mqtt-client-adapter logs filtered by reconnect "
                        "in the last 6 hours. Status: no_entries.\n"
                        "Service: iot-mqtt-client-adapter\n"
                        "Contains: reconnect"
                    ),
                },
            ],
        )

        self.assertIn("contains reconnect", resolved)
        tool, params, _ = agent.classify_tool(resolved)
        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params["service"], "iot-mqtt-client-adapter")
        self.assertEqual(params["contains"], "reconnect")
        self.assertEqual(params["hours_back"], 24)

    def test_widen_log_followup_stays_on_resolved_log_target(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        agent.model = MagicMock()

        answer = agent.build_grafana_logs_answer({
            "answer_language": "en",
            "current_user_input": "Widen the time range for the log check.",
            "request": {
                "service": "iot-mqtt-client-adapter",
                "hours_back": 24,
            },
            "logs": [],
        })

        planned, _ = agent.apply_followup_planner(
            answer,
            {
                "selected_tool": "grafana_logs",
                "user_input": "Widen the time range for the log check.",
                "conversation_context": [{
                    "role": "assistant",
                    "content": (
                        "# Grafana Log Check Result\n"
                        "Checked iot-mqtt-client-adapter logs without a keyword "
                        "filter in the last 6 hours. Status: no_entries."
                    ),
                }],
            },
        )

        agent.model.invoke.assert_not_called()
        followups = planned.split("## Follow-up Questions")[-1]
        self.assertNotIn("Check RabbitMQ queue backlog", followups)
        self.assertNotIn("Check RabbitMQ throughput", followups)

    def test_wider_log_search_keeps_device_filter_from_flow_evidence_line(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b"

        resolved = agent.resolve_contextual_user_input(
            "Try a wider time range for the log search.",
            [
                {
                    "role": "assistant",
                    "content": (
                        "# OneM2M Telemetry Uplink Flow Check Result\n"
                        "## 3. Logs / Grafana Evidence\n"
                        "grafana_logs: queried MCP loki_query_range; "
                        f"service=notify; contains={device_id}; hours_back=6; "
                        "0 entries matched\n"
                    ),
                },
            ],
        )

        self.assertIn("service notify", resolved)
        self.assertIn(f"contains {device_id}", resolved)
        self.assertIn("last 24 hours", resolved)
        tool, params, _ = agent.classify_tool(resolved)
        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params["service"], "notify")
        self.assertEqual(params["contains"], device_id)
        self.assertEqual(params["hours_back"], 24)

    def test_recent_errors_log_followup_keeps_previous_keyword_and_window(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "Sc71f749c-9fd5-4ee6-93fa-c14ee9e5871b"

        resolved = agent.resolve_contextual_user_input(
            "Check recent errors for service notify",
            [
                {
                    "role": "assistant",
                    "content": (
                        "# Grafana Log Check Result\n"
                        f"Checked notify logs filtered by {device_id} "
                        "in the last 48 hours. Status: no_entries.\n"
                        "Service: notify\n"
                        f"Contains: {device_id}\n"
                        "Time range: 1784532044 -> 1784704844 "
                        "(last 48 hours)"
                    ),
                },
            ],
        )

        self.assertIn(f"contains {device_id}", resolved)
        self.assertIn("last 48 hours", resolved)
        tool, params, _ = agent.classify_tool(resolved)
        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params["service"], "notify")
        self.assertEqual(params["contains"], device_id)
        self.assertEqual(params["hours_back"], 48)

    def test_broker_side_log_followup_keeps_window_without_device_filter(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        device_id = "S3e1c21c3-7aad-415a-a1cd-03d3d0c6a73f"

        resolved = agent.resolve_contextual_user_input(
            "Check EMQX logs for broker-side errors",
            [
                {
                    "role": "assistant",
                    "content": (
                        "# Grafana Log Check Result\n"
                        "Checked iot-mqtt-client-adapter logs filtered by "
                        f"{device_id} in the last 24 hours. Status: no_entries.\n"
                        "Service: iot-mqtt-client-adapter\n"
                        f"Contains: {device_id}\n"
                        "Time range: 1784687354 -> 1784773754 "
                        "(last 24 hours)"
                    ),
                },
            ],
        )

        self.assertNotIn(f"contains {device_id}", resolved)
        self.assertIn("last 24 hours", resolved)
        tool, params, _ = agent.classify_tool(resolved)
        self.assertEqual(tool, "grafana_logs")
        self.assertEqual(params["service"], "emqx")
        self.assertEqual(params["hours_back"], 24)
        self.assertEqual(params["level"], "error|warn")
        self.assertNotIn("contains", params)

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
        log_workflows = [
            workflow for workflow in planned if workflow["tool"] == "grafana_logs"
        ]
        self.assertEqual(
            {workflow["params"]["service"] for workflow in log_workflows},
            {"iot-http-api", "iot-mqtt-client-adapter"},
        )
        for log_workflow in log_workflows:
            self.assertEqual(log_workflow["params"]["contains"], "dvi-1")
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

    def test_ioa_v3_device_drilldown_stream_uses_company_mongodb_evidence(self):
        original_flag = os.environ.get("IOA_V3_SEMANTIC_PLANNER_ENABLED")
        os.environ["IOA_V3_SEMANTIC_PLANNER_ENABLED"] = "false"
        model = MagicMock()
        model.invoke.return_value.content = (
            "Device dev-1 is critical based on company MongoDB evidence."
        )
        model.invoke.return_value.response_metadata = {}
        agent = IOAV3LangGraphN8nAgent(model=model)

        try:
            with patch(
                "agents.ioa_v3_agent.get_company_device_drilldown_context",
                return_value={
                    "source": "company_mongodb",
                    "tool": "get_company_device_drilldown",
                    "query_device_id": "dev-1",
                    "device_match_count": 1,
                    "db_audit_status": "runtime_audit_available",
                    "db_audit": [{
                        "actor": "company-llm-tools",
                        "operation": "find",
                        "namespace": "datamgmt.CIN",
                        "query": {"con.deviceId": "dev-1"},
                        "projection": {"_id": 0, "con": 1, "ct": 1},
                        "effective_limit": 500,
                        "max_time_ms": 5000,
                        "credentials_redacted": True,
                        "mutating": False,
                    }],
                    "devices": [{
                        "device_id": "dev-1",
                        "status": "critical",
                        "metrics": [{"name": "temperature", "value": 83}],
                        "recent_history": [{
                            "timestamp": "2026-07-16T09:00:00Z",
                            "metrics": [{"name": "temperature", "value": 83}],
                        }],
                    }],
                    "alerts": [{
                        "alert_id": "alert-1",
                        "device_id": "dev-1",
                        "severity": "critical",
                        "title": "Temperature above threshold",
                    }],
                    "evidence_gaps": [],
                    "next_diagnostic_step": "Check recent telemetry trend.",
                },
            ):
                events = list(agent.run_stream(
                    "vì sao device dev-1 đang critical?",
                    selected_source="company",
                    source_resolution={
                        "selected_source": "company",
                        "active_source": "company_mongodb",
                    },
                    user_id=1,
                ))
        finally:
            if original_flag is None:
                os.environ.pop("IOA_V3_SEMANTIC_PLANNER_ENABLED", None)
            else:
                os.environ["IOA_V3_SEMANTIC_PLANNER_ENABLED"] = original_flag

        observations = [
            event for event in events
            if event.get("type") == "observation"
        ]
        run_step = next(
            event["observation"]["output"]
            for event in observations
            if event["observation"]["output"].get("workflow_count") == 1
        )
        execution = run_step["executions"][0]
        self.assertEqual(execution["tool"], "get_company_device_drilldown")
        self.assertEqual(execution["evidence"]["query_device_id"], "dev-1")
        self.assertIn("query_commands", execution)
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
            "agents.ioa_v3_agent.query_iot_platform_metric_via_mcp",
            return_value={
                "source": "mcp_server",
                "mcp_tool": "grafana_query",
                "tool": "grafana_redis_health",
                "request": {},
                "queries": {
                    "connected_clients": {
                        "data": {
                            "result": [{
                                "metric": {},
                                "value": [1710000000, "10"],
                            }]
                        }
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
            execution.get("source") == "mcp_server"
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
        self.assertIn("| `IDENTITY` | **Missing** |", result["final_answer"])

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

    def test_platform_service_health_uses_deterministic_answer_format(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        answer = agent.build_deterministic_answer({
            "user_input": "Check platform service health",
            "selected_tool": "grafana_platform_service_health",
            "tool_outputs": [{
                "tool": "grafana_platform_service_health",
                "result": {
                    "level": "warning",
                    "body": {
                        "dashboards": {
                            "http": "warning",
                            "k8s": "good",
                            "rabbitmq": "good",
                            "redis": "warning",
                        },
                        "overall_verdict": "warning",
                    },
                },
            }],
        })

        self.assertIn("# Platform Service Health Check Result", answer)
        self.assertIn("## 1. Summary", answer)
        self.assertIn("## 7. Recommended Next Action", answer)
        self.assertIn("| http | warning |", answer)
        self.assertNotIn("\nSummary\n", answer)

    def test_ioa_v3_answer_prompt_preserves_user_language(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)
        state = {
            "user_input": "kiểm tra thiết bị SmartAsset_9b47fedc",
            "selected_tool": "get_company_onem2m_device_resources",
            "tool_outputs": [],
        }

        prompt = agent.build_answer_prompt(state)

        self.assertIn("Reply in the same primary language", prompt)
        self.assertIn("Vietnamese", prompt)
        self.assertIn("technical identifiers", prompt)
        self.assertIn("SmartAsset_9b47fedc", prompt)


if __name__ == "__main__":
    unittest.main()
