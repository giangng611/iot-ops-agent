# Telegram PoC

The Telegram PoC adds Telegram as a second chat client for the existing IoT Ops Agent backend.

```text
Telegram message
→ Flask /api/telegram/webhook
→ IOA v3 · Ops Graph
→ reasoning persistence/events when configured
→ formatted final answer
→ Telegram reply + optional web synchronization
```

The web app and existing diagnosis endpoints remain unchanged.

## Environment

```env
PUBLIC_BASE_URL=https://your-app-host
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_WEBHOOK_SECRET=your_random_webhook_secret
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
TELEGRAM_LINK_CODE_TTL_MINUTES=15
```

`TELEGRAM_ALLOWED_USER_IDS` is an optional outer allowlist. Set it before
company testing so only approved Telegram accounts can reach the bot.

Every Telegram account must also be linked to an IoT Ops Agent user in the
application database. The Telegram runtime fails closed when the Telegram user
ID is missing, unlinked, inactive, or outside the optional allowlist.

## Account Linking

Recommended user flow:

```text
1. User logs in to the IoT Ops Agent web platform.
2. User opens Profile -> Telegram.
3. User clicks Generate Link Code.
4. The web UI shows a one-time command such as /link ABCD2345.
5. User sends that command to the Telegram bot.
6. Telegram stores telegram_user_id -> app user_id.
```

Security properties:

* Link codes are generated only for authenticated web users.
* Link codes are stored as SHA-256 hashes, not plaintext.
* Link codes expire after `TELEGRAM_LINK_CODE_TTL_MINUTES`, default 15.
* Link codes are single-use.
* New self-service Telegram links get `role=viewer` and
  `allowed_data_sources=simulator`.
* Company DB access is never self-granted by `/link`.
* New IoT Ops Agent accounts default to simulator on the web platform.
* When an admin grants `simulator,company`, the user's platform default can be
  set to Company DB by the grant script.

Admin bootstrap or emergency mapping is still available with:

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
https://your-app-host/api/telegram/webhook
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
/ingestion
/apihealth
/infra
/companyfleet
/coverage
/pocalerts
/disconnected
/ruleready
/link CODE
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

Telegram slash commands reuse the same default prompt catalog used by the web
Prompts tab where possible. For example, `/overview`, `/ingestion`,
`/apihealth`, `/infra`, `/companyfleet`, `/coverage`, `/pocalerts`,
`/disconnected`, and `/ruleready` resolve to the corresponding default prompt
commands from `services.prompt_service.DEFAULT_PROMPTS`. Free-form Telegram
messages are still passed through as written, so web prompt text can be copied
directly into Telegram when a command alias does not exist.

## Test Company DB Through Localhost

Telegram requires a public HTTPS webhook, so it cannot call `localhost`
directly. Use a temporary Cloudflare tunnel:

```bash
APP_DB_BACKEND=supabase \
APP_DB_FALLBACK_ENABLED=false \
SUPABASE_DB_URL="postgresql://postgres.project-ref:password@region.pooler.supabase.com:6543/postgres" \
POSTGRES_POOL_TIMEOUT_SECONDS=5 \
POSTGRES_CONNECT_TIMEOUT_SECONDS=5 \
POSTGRES_STATEMENT_TIMEOUT_MS=4000 \
PORT=5001 \
python app.py

cloudflared tunnel --url http://127.0.0.1:5001
```

Do not use SQLite fallback for this test. If Supabase cannot be reached, fix
the Supabase connection string, network, or pooler setting before testing
Telegram linking.

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

For a company-data test that should start before the UI is opened, grant the
user Company DB access first:

```bash
python -m scripts.upsert_telegram_identity \
  --telegram-user-id 123456789 \
  --username company-operator \
  --telegram-username operator_handle \
  --role operator \
  --data-sources simulator,company
```

The grant updates both Telegram scope and the web platform data-source policy.
Users without the `company` grant cannot switch the web workspace to Company
DB.

After testing, restore the deployed webhook:

```bash
python -m scripts.configure_telegram_webhook \
  --base-url https://your-app-host
```

## Notes

Telegram can run without Dify because it calls Flask directly and Flask calls
the in-process IOA v3 Ops Graph runtime. Company answers require the Flask
runtime to reach the MCP server. IOA v3 then collects Company MongoDB, Loki,
and Grafana/Prometheus evidence through MCP according to the selected plan.

The local tunnel is intended for a controlled PoC only. The temporary URL
changes whenever the quick tunnel restarts.
