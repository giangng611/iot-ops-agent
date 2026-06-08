# Telegram PoC

The Telegram PoC adds Telegram as a second chat client for the existing IoT Ops Agent backend.

```text
Telegram message
→ Flask /api/telegram/webhook
→ IOA v2 · LangGraph
→ final answer only
→ Telegram reply
```

The web app and existing diagnosis endpoints remain unchanged.

## Environment

```env
PUBLIC_BASE_URL=https://iot-ops-agent.onrender.com
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_WEBHOOK_SECRET=your_random_webhook_secret
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
TELEGRAM_HISTORY_USER_ID=1
```

`TELEGRAM_ALLOWED_USER_IDS` is optional for local testing. Set it before company testing so only approved Telegram accounts can use the bot.

`TELEGRAM_HISTORY_USER_ID` is optional. When set, each Telegram request is saved as a platform chat owned by that app user, including the assistant final answer, reasoning steps, and token usage when available.

## Configure Webhook

After deploying the branch and setting the environment variables, run:

```bash
python3 scripts/configure_telegram_webhook.py
```

This registers:

```text
https://iot-ops-agent.onrender.com/api/telegram/webhook
```

with Telegram.

## Bot Behavior

Supported help commands:

```text
/
/start
/help
```

They return the initial prompt list:

```text
/overview system health
/check all unhealthy devices
/show devices with alarms
/diagnose system issue
/check devices with delayed heartbeat
/diagnose gateway-001
```

Any other text is sent to the existing LangGraph runtime and the bot replies with only the final answer.

## Notes

The current Render deployment can run this PoC without localhost-only n8n or Dify dependencies because Telegram calls Flask directly and Flask calls the in-process LangGraph agent.

Real company DB integration should be handled separately after this Telegram input channel is proven end-to-end.
