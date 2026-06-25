# Sniper Alert

Sniper Alert is a private options alert monitoring system for John. It watches or ingests posts from `@StockOptions888`, detects options alerts, parses contracts, stores raw and parsed data, scores enterability conservatively, notifies John privately, and tracks claimed performance separately from verified or paper performance.

This is not a live trading bot, not a public X/Twitter engagement bot, and not financial advice software.

## Naming

- Project: **Sniper Alert**
- Source account: `@StockOptions888`
- Runtime agent identity: **Lux**
- Existing always-on framework: **OpenClaw/Lux**
- Repo/module: `lux-options-piggyback-agent`
- Sprint 1 purpose: private options alert monitoring, journaling, scoring, notification, and paper tracking

Lux is the always-on VPS runtime agent that runs the Sniper Alert monitor. Lux is not the product name, trading strategy, or trusted trading brain. Old OpenClaw/Lux code may be inspected for infrastructure patterns only, such as service management, logging, environment loading, command routing, and health checks.

## Sprint 1 Does

- Run without broker keys.
- Run without market data credentials.
- Treat Tradier as the selected future broker integration path.
- Include Tradier config placeholders and broker stubs only.
- Support manual ingest for testing.
- Support file-based source polling for VPS operation.
- Classify posts as `new_trade_alert`, `trade_update`, `claimed_result`, `general_market_commentary`, `non_trade`, or `unknown`.
- Parse tweet-style options alerts such as `$HNI 45 CALL 7/17 avg .75`.
- Store data in SQLite at `data/sniper_alert.sqlite`.
- Write disk logs to `logs/sniper_alert.log`.
- Notify via console or Telegram.
- Track source-claimed performance as unverified until market data supports it.
- Support local paper tracking in `paper_trade` mode.
- Run under Lux/OpenClaw in Hostinger Docker Manager.

## Sprint 1 Does Not Do

- No live trading.
- No live Tradier execution.
- No broker API order submission.
- No broker keys.
- No autonomous order placement.
- No public X engagement.
- No posting, replying, liking, following, reposting, or DMing.
- No unapproved risk sizing.
- No old OpenClaw trading logic.

## Guardrails

- Default autonomy is `monitor_only`.
- The only Sprint 1 autonomy modes are `monitor_only` and `paper_trade`.
- Broker execution is disabled.
- Tradier is selected as the future broker path, but `BROKER_MODE=none` keeps it inactive today.
- `BROKER_EXECUTION_ENABLED=false` is required behavior for this sprint.
- `REQUIRE_HUMAN_APPROVAL=true` is required behavior for any future broker path.
- Public X engagement is disabled.
- Kill switch blocks everything except audit logging and health reporting.
- Missing quote data returns `needs_review`.
- LLM fallback is rules-first and only runs on low-confidence classification/parsing when enabled and `OPENAI_API_KEY` is configured.
- LLM output can classify, extract, or summarize only. It can never approve trades, size trades, override kill switch, or change autonomy.
- All important actions are written to the SQLite audit log.

## Setup

```bash
cd lux-options-piggyback-agent
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main run-once
python -m pytest
```

The app runs with this safe test configuration:

```env
SOURCE_MODE=manual
LLM_ENABLED=true
LLM_REQUIRED=false
LLM_PROVIDER=openai
LLM_MODEL_FAST=gpt-5.4-nano
LLM_MODEL_REVIEW=gpt-5.4-mini
LLM_USE_DEEP=false
MARKET_DATA_PROVIDER=none
BROKER_PROVIDER=tradier
BROKER_MODE=none
BROKER_EXECUTION_ENABLED=false
REQUIRE_HUMAN_APPROVAL=true
TRADIER_ENV=sandbox
PUBLIC_X_ENGAGEMENT=false
```

## Runtime Commands

```bash
python -m app.main run-once
python -m app.main daemon
python -m app.main status
python -m app.main pause
python -m app.main resume
python -m app.main kill-switch on
python -m app.main kill-switch off
python -m app.main autonomy monitor_only
python -m app.main autonomy paper_trade
python -m app.main health
python -m app.main logs
python -m app.main ingest-manual --text '$HNI 45 CALL 7/17 avg .75'
python -m app.main quote-manual --alert-id 1 --bid 0.70 --ask 0.85 --last 0.80
python -m app.main alerts
python -m app.main paper
python -m app.main audit
```

## Manual Ingest Testing

```bash
python -m app.main ingest-manual --text '$HNI 45 CALL 7/17 avg .75'
python -m app.main alerts
python -m app.main audit
```

With `MARKET_DATA_PROVIDER=none`, quote-dependent alerts are scored as `needs_review`.

## Today's Acceptance Test

```bash
python -m app.main ingest-manual --text '$HNI 45 CALL 7/17 avg .75'
python -m app.main status
python -m app.main alerts
python -m app.main audit
python -m pytest
```

Expected result: Lux can run Sniper Alert on the VPS, process a manual alert, parse the contract, save it to SQLite, score it conservatively, mark it as `needs_review` when quote data is missing, and notify John privately.

## Tradier Path

Tradier is the selected future broker integration path. Sprint 1 only includes configuration placeholders and a disabled broker stub:

```env
BROKER_PROVIDER=tradier
BROKER_MODE=none
BROKER_EXECUTION_ENABLED=false
REQUIRE_HUMAN_APPROVAL=true
TRADIER_ENV=sandbox
TRADIER_ACCESS_TOKEN=
TRADIER_ACCOUNT_ID=
```

No Tradier credentials are required. No live orders are submitted. No autonomous trading is implemented.

## Notifications

Default local testing falls back to console notifications. For Telegram, set:

```env
NOTIFICATION_PROVIDER=telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Notifications say `review`, `watch`, `paper candidate`, or `too late`. They never say “buy now” or “approved trade.”

## Hostinger Docker Quick Deploy

Primary deployment target is a new Sniper Alert container next to the existing OpenClaw container. Do not modify the current OpenClaw container.

```text
Hostinger VPS
  Docker Manager
    project: openclaw-3jb6
      existing container: openclaw-3jb6-openclaw-1
        Lux/OpenClaw runtime
      new container: sniper-alert
        Sniper Alert monitor
        command: python -m app.main daemon
        data volume: sniper_alert_data
        logs volume: sniper_alert_logs
```

Docker environment variables are the primary credential-loading path on Hostinger. `.env` is supported for local development as a fallback only. The app reads real environment variables first and only uses `.env` values when a variable is missing.

Hostinger hPanel steps:

1. Go to Hostinger hPanel.
2. Open VPS.
3. Open Docker Manager.
4. Select project `openclaw-3jb6`.
5. Keep `openclaw-3jb6-openclaw-1` unchanged.
6. Add a new container named `sniper-alert`.
7. Use the Sniper Alert image/build context.
8. Set the run command to `python -m app.main daemon`.
9. Add Docker volumes for `/app/data` and `/app/logs`.
10. Add the safe environment variables below.
11. Save and deploy the new `sniper-alert` container.
12. Confirm both containers are running.
13. Check `sniper-alert` logs.

Safe Docker environment variables:

```env
APP_NAME=Sniper Alert
SOURCE_MODE=manual
MARKET_DATA_PROVIDER=none
BROKER_PROVIDER=tradier
BROKER_MODE=none
BROKER_EXECUTION_ENABLED=false
REQUIRE_HUMAN_APPROVAL=true
TRADIER_ENV=sandbox
AUTONOMY_LEVEL=monitor_only
PUBLIC_X_ENGAGEMENT=false
KILL_SWITCH=false
LLM_ENABLED=false
LLM_REQUIRED=false
NOTIFICATION_PROVIDER=console
DATABASE_URL=sqlite:////app/data/sniper_alert.sqlite
LOG_FILE=/app/logs/sniper_alert.log
```

Terminal checks:

```bash
docker ps
docker exec sniper-alert printenv | grep -E "APP_NAME|SOURCE_MODE|MARKET_DATA|LLM|TELEGRAM|BROKER|TRADIER|AUTONOMY|KILL_SWITCH"
docker logs sniper-alert --tail 100
```

Do not paste secret values into tickets, docs, or logs. The app status output only reports whether `OPENAI_API_KEY` is configured, not the value.

Before daemon mode, run these acceptance commands inside the `sniper-alert` container or app directory:

```bash
python -m app.main status
python -m app.main ingest-manual --text '$HNI 45 CALL 7/17 avg .75'
python -m app.main alerts
python -m app.main audit
```

Expected result: the `sniper-alert` container processes the manual alert, saves it to SQLite, scores it as `needs_review`, and does not attempt any broker action. It does not require OpenAI, X, Tradier, broker credentials, or live market data.

## Optional Systemd Deployment

Systemd is secondary and optional. Use it only outside the Hostinger Docker Manager setup.

Optional systemd setup:

```bash
sudo cp deploy/lux-options-agent.service /etc/systemd/system/lux-options-agent.service
sudo systemctl daemon-reload
sudo systemctl enable lux-options-agent
sudo systemctl start lux-options-agent
sudo systemctl status lux-options-agent
```

The service runs:

```bash
python -m app.main daemon
```

and restarts automatically if it crashes.

## Local Docker Compose

Docker Compose is optional for local or non-Hostinger testing:

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

## Data Model

SQLite tables are created automatically on first run:

- `social_posts`
- `parsed_alerts`
- `trade_updates`
- `quotes`
- `scores`
- `paper_positions`
- `claimed_performance`
- `audit_events`
- `control_state`
- `health_checks`

Claimed performance is stored separately and defaults to `unverified`.

## Why No Live Trading Exists

Sprint 1 proves the core monitoring workflow before any execution discussion. The useful first milestone is evidence: raw posts, parsed alerts, conservative scores, private notifications, paper tracking, and claimed-versus-verified performance. No code path places a real trade in this repo, including Tradier.
