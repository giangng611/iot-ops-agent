import os
import unittest
from unittest.mock import MagicMock, patch

from agents.ioa_v3_agent import IOAV3LangGraphN8nAgent
from services.grafana_tool_registry import (
    build_grafana_workflow_policy,
    get_grafana_tool_by_name,
    get_kpi_rules_for_tool,
)
from services.n8n_gateway_service import (
    build_n8n_v3_payload,
    get_n8n_v3_webhook_url,
)


class IOAV3WorkflowTests(unittest.TestCase):
    def test_grafana_registry_exposes_allowlisted_tools(self):
        tool = get_grafana_tool_by_name("grafana_queue_backlog")
        policy = build_grafana_workflow_policy()

        self.assertEqual(tool["path"], "/grafana/queue-backlog")
        self.assertIn("unapproved_grafana_endpoint", policy["forbidden_capabilities"])
        self.assertTrue(any(
            item["tool"] == "grafana_queue_backlog"
            for item in policy["allowed_workflows"]
        ))

    def test_kpi_rules_are_mapped_to_grafana_tools(self):
        rules = get_kpi_rules_for_tool("grafana_queue_backlog")

        self.assertTrue(rules)
        self.assertEqual(rules[0]["kpi"], "Queue Backlog")
        self.assertEqual(rules[0]["priority"], "Core")

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

    def test_v3_webhook_does_not_fallback_to_legacy_n8n_url(self):
        original_v3 = os.environ.pop("N8N_V3_WEBHOOK_URL", None)
        original_grafana = os.environ.pop("N8N_GRAFANA_WEBHOOK_URL", None)
        original_legacy = os.environ.get("N8N_WEBHOOK_URL")
        os.environ["N8N_WEBHOOK_URL"] = "http://localhost:5678/webhook/iot-ops-eval"

        try:
            self.assertIsNone(get_n8n_v3_webhook_url())
        finally:
            if original_v3 is not None:
                os.environ["N8N_V3_WEBHOOK_URL"] = original_v3
            if original_grafana is not None:
                os.environ["N8N_GRAFANA_WEBHOOK_URL"] = original_grafana
            if original_legacy is None:
                os.environ.pop("N8N_WEBHOOK_URL", None)
            else:
                os.environ["N8N_WEBHOOK_URL"] = original_legacy

    def test_ioa_v3_selects_grafana_tool_from_prompt(self):
        agent = IOAV3LangGraphN8nAgent.__new__(IOAV3LangGraphN8nAgent)

        tool, params, reason = agent.classify_grafana_tool(
            "check redis health"
        )

        self.assertEqual(tool, "grafana_redis_health")
        self.assertEqual(params, {})
        self.assertEqual(reason, "redis_keywords")

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
            event["observation"]["output"].get("source") == "n8n_grafana_gateway"
            for event in observations
        ))
        self.assertTrue(any(
            event["observation"]["output"].get("rule_source")
            == "config/grafana_kpi_rules.json"
            for event in observations
        ))
        self.assertEqual(events[-1]["type"], "final")


if __name__ == "__main__":
    unittest.main()
