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
TELEGRAM_DEFAULT_DATA_SOURCE=simulator
```

`TELEGRAM_ALLOWED_USER_IDS` is an optional outer allowlist. Set it before
company testing so only approved Telegram accounts can reach the bot.

Every Telegram account must also be mapped to an IoT Ops Agent user in the
application database. The Telegram runtime fails closed when the Telegram user
ID is missing, unmapped, inactive, or outside the optional allowlist.

Create or update a mapping with:

```bash
python -m scripts.upsert_telegram_identity \
  --telegram-user-id 123456789 \
  --username company-operator \
  --telegram-username operator_handle \
  --role operator \
  --data-sources simulator,company
```

For a lower-risk user, grant simulator only:

```bash
python -m scripts.upsert_telegram_identity \
  --telegram-user-id 987654321 \
  --username demo-viewer \
  --role viewer \
  --data-sources simulator
```

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

Any other text is sent to the existing LangGraph runtime only after identity
and data-source authorization pass. Telegram receives the formatted final
answer. The platform stores the request, reasoning steps, final answer, and
token metadata under the mapped IoT Ops Agent user.

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

Keep both processes running. Open the local platform as the IoT Ops Agent user
mapped to the Telegram account, select `Company DB`, and then send a Telegram
command. The source choice is remembered in process for that mapped user. The
Telegram identity must include `company` in `allowed_data_sources`; otherwise
the request is rejected before LangGraph runs.

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
