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
TELEGRAM_DEFAULT_DATA_SOURCE=simulator
```

`TELEGRAM_ALLOWED_USER_IDS` is optional for local testing. Set it before company testing so only approved Telegram accounts can use the bot.

`TELEGRAM_HISTORY_USER_ID` is optional. When set, each Telegram request is saved as a platform chat owned by that app user, including the assistant final answer, reasoning steps, and token usage when available.

## Configure Webhook

After deploying and setting the environment variables, run:

```bash
python3 scripts/configure_telegram_webhook.py
```

This registers the webhook and the Telegram `/` command menu:

```text
https://iot-ops-agent.onrender.com/api/telegram/webhook
```

with Telegram.

## Bot Behavior

Supported commands:

```text
/overview
/unhealthy
/alarms
/diagnose
/heartbeat
/help
```

`/diagnose` can optionally include a device ID:

```text
/diagnose gateway-001
```

Any other text is sent to the existing LangGraph runtime and the bot replies with only the final answer.

## Test Company DB Through Localhost

Telegram requires a public HTTPS webhook, so it cannot call `localhost`
directly. Use a temporary Cloudflare tunnel:

```bash
python3 app.py
cloudflared tunnel --url http://127.0.0.1:5001
```

Copy the generated `https://...trycloudflare.com` URL, then point Telegram to
the local app:

```bash
python3 scripts/configure_telegram_webhook.py \
  --base-url https://your-tunnel.trycloudflare.com
```

Keep both processes running. Open the local platform, select `Company DB`, and
then send a Telegram command. The local Flask process will handle the webhook
and query the company MongoDB through the machine's internal network access.

For a demo that should start on company data before the UI is opened, launch
the local app with:

```bash
TELEGRAM_DEFAULT_DATA_SOURCE=company PORT=5001 python3 app.py
```

Once the user changes the data source in the UI, that session choice takes
priority over the default.

After testing, restore the deployed webhook:

```bash
python3 scripts/configure_telegram_webhook.py \
  --base-url https://iot-ops-agent.onrender.com
```

## Notes

The current Render deployment can run this PoC without localhost-only n8n or Dify dependencies because Telegram calls Flask directly and Flask calls the in-process LangGraph agent.

The local tunnel is intended for a controlled PoC only. The temporary URL
changes whenever the quick tunnel restarts.
