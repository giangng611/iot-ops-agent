import argparse
import json
import os
import sys

import requests

from services.n8n_gateway_service import build_n8n_v3_payload


def main():
    parser = argparse.ArgumentParser(
        description="Probe the IOA v3 n8n Grafana gateway webhook.",
    )
    parser.add_argument(
        "--webhook-url",
        default=os.getenv(
            "N8N_V3_WEBHOOK_URL",
            "http://localhost:5679/webhook/grafana-ops-gateway",
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
    args = parser.parse_args()

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

    response = requests.post(args.webhook_url, json=payload, timeout=20)

    print(f"status_code={response.status_code}")

    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(response.text)

    if response.status_code >= 400:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
