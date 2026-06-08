import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.telegram_service import build_set_webhook_payload


def main():
    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL")

    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required.")

    if not public_base_url:
        raise RuntimeError(
            "PUBLIC_BASE_URL or RENDER_EXTERNAL_URL is required. "
            "Example: https://iot-ops-agent.onrender.com"
        )

    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        data=build_set_webhook_payload(public_base_url),
        timeout=20,
    )
    response.raise_for_status()

    print(response.text)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Failed to configure Telegram webhook: {exc}", file=sys.stderr)
        raise
