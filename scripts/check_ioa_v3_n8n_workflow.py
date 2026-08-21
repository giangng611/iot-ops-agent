import argparse
import json
import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.n8n_gateway_service import build_n8n_v3_payload


def main():
    parser = argparse.ArgumentParser(
        description="Probe the IOA v3 n8n Grafana gateway webhook.",
    )
    parser.add_argument(
        "--webhook-url",
        default=os.getenv(
            "N8N_V3_WEBHOOK_URL",
            "http://localhost:5678/webhook/grafana-ops-gateway",
        ),
        help="n8n IOA v3 webhook URL.",
    )
    parser.add_argument(
        "--tool",
        default="grafana_redis_health",
        help="Grafana tool name from config/grafana_tools.json.",
    )
    parser.add_argument(
        "--message",
        default="Check Redis health",
        help="Synthetic user message to include in the workflow payload.",
    )
    parser.add_argument(
        "--grafana-base-url",
        default=None,
        help=(
            "Override the Grafana Dashboard Client API base URL sent to n8n. "
            "This should be an API adapter URL, not a Grafana dashboard UI URL."
        ),
    )
    args = parser.parse_args()

    if args.grafana_base_url:
        os.environ["GRAFANA_DASHBOARD_CLIENT_URL"] = args.grafana_base_url

    payload = build_n8n_v3_payload(
        user_input=args.message,
        selected_tool=args.tool,
        params={},
        source_resolution={
            "selected_source": "company",
            "active_source": "company_mongodb",
        },
        user_id="local-probe",
    )

    print(f"grafana_base_url={payload['grafana_client']['base_url']}")
    print(f"webhook_url={args.webhook_url}")
    print(f"workflow_path={payload['workflow']['path']}")

    response = requests.post(args.webhook_url, json=payload, timeout=20)

    print(f"status_code={response.status_code}")
    response_text = response.text.strip()

    if not response_text:
        print(
            "empty_response_body=true\n"
            "n8n accepted the webhook but did not return JSON. In the n8n "
            "workflow, open the Webhook node and set Respond to "
            "\"When Last Node Finishes\", then make sure the last node is "
            "\"Normalize IOA v3 Response\", saved, and the workflow is active."
        )
        return 1

    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(response_text)
        print("invalid_json_response=true")
        return 1

    if response.status_code >= 400:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
