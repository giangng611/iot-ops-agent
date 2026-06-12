# Telegram PoC

The Telegram PoC adds Telegram as a second chat client for the existing IoT Ops Agent backend.

```text
Telegram message
→ Flask /api/telegram/webhook
→ IOA v2 · LangGraph
→ reasoning persistence/events when configured
→ formatted final answer
→ Telegram reply + optional web synchronization
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
python -m scripts.configure_telegram_webhook
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
/companyfleet
/coverage
/pocalerts
/disconnected
/ruleready
/help
```

`/diagnose` can optionally include a device ID:

```text
/diagnose gateway-001
```

Any other text is sent to the existing LangGraph runtime. Telegram receives
the formatted final answer. With `TELEGRAM_HISTORY_USER_ID`, the platform also
stores and emits the reasoning steps and token metadata.

## Test Company DB Through Localhost

Telegram requires a public HTTPS webhook, so it cannot call `localhost`
directly. Use a temporary Cloudflare tunnel:

```bash
python app.py
cloudflared tunnel --url http://127.0.0.1:5001
```

Copy the generated `https://...trycloudflare.com` URL, then point Telegram to
the local app:

```bash
python -m scripts.configure_telegram_webhook \
  --base-url https://your-tunnel.trycloudflare.com
```

Keep both processes running. Open the local platform as the user identified by
`TELEGRAM_HISTORY_USER_ID`, select `Company DB`, and then send a Telegram
command. The source choice is remembered in process for that user.

For a demo that should start on company data before the UI is opened, launch
the local app with:

```bash
TELEGRAM_DEFAULT_DATA_SOURCE=company PORT=5002 python app.py
```

Once the mapped user changes the source in the UI, that in-process choice
takes priority. After an app restart, the default is used until the UI source
is remembered again.

After testing, restore the deployed webhook:

```bash
python -m scripts.configure_telegram_webhook \
  --base-url https://iot-ops-agent.onrender.com
```

## Notes

The current Render deployment can run this PoC without n8n or Dify because
Telegram calls Flask directly and Flask calls the in-process LangGraph agent.
Company answers still require the Flask runtime to reach Company MongoDB.

The local tunnel is intended for a controlled PoC only. The temporary URL
changes whenever the quick tunnel restarts.
