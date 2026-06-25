# Sniper Alert

Sniper Alert is a private options alert monitoring system for John. It watches or ingests posts from `@StockOptions888`, detects options alerts, parses contracts, stores raw and parsed data, scores enterability conservatively, notifies John privately, and tracks claimed performance separately from verified or paper performance.

This is not a live trading bot, not a public X/Twitter engagement bot, and not financial advice software.

## Naming

- Project: **Sniper Alert**
- Source account: `@StockOptions888`
- Runtime agent identity: **Lux**
- Existing always-on framework: **OpenClaw/Lux**
- Repo/module: `lux-options-piggyback-agent`
- Sprint 2B purpose: private JSONL source monitoring, conservative scoring, notifications, paper tracking, source exit detection, and performance reporting

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
- Track source-claimed performance as not enough data until market or paper data supports it.
- Support local paper tracking in `paper_trade` mode.
- Run under Lux/OpenClaw in Hostinger Docker Manager.

## Sprint 2B Adds

- Run as a separate `sniper-alert` Docker container next to OpenClaw.
- Watch a private JSONL bridge at `/app/input/source_posts.jsonl`.
- Append source posts with `scripts/append_source_post.py`.
- Deduplicate by `source_post_id`.
- Audit invalid JSONL lines and duplicate skips.
- Classify `source_exit_update` separately from claimed results.
- Detect exit language such as sold, trim, take profit, cut, stopped, out, closed, runner, and leave runners.
- Detect claimed-result language such as winner, banked, congrats, percent-gain claims, and “from .20 to 1.00”.
- Keep Tradier read-only and disabled for live execution.
- Open local paper copies in `paper_trade` mode when an alert has at least an alert price.
- Generate performance reports with source-claimed, local paper, sandbox, verified market, and insufficient-data buckets.

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

- Default Sprint 2B autonomy is `paper_trade` for local paper tracking only.
- The only Sprint 1 autonomy modes are `monitor_only` and `paper_trade`.
- Broker execution is disabled.
- Tradier is selected as the future broker path, but `BROKER_MODE=read_only` keeps it non-executing.
- `BROKER_EXECUTION_ENABLED=false` is required behavior.
- `ENABLE_TRADIER_SANDBOX_ORDERS=false` by default.
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
SOURCE_MODE=jsonl_watch
SOURCE_JSONL_PATH=/app/input/source_posts.jsonl
LLM_ENABLED=false
LLM_REQUIRED=false
LLM_PROVIDER=openai
LLM_MODEL_FAST=gpt-5.4-nano
LLM_MODEL_REVIEW=gpt-5.4-mini
LLM_USE_DEEP=false
MARKET_DATA_PROVIDER=tradier
BROKER_PROVIDER=tradier
BROKER_MODE=read_only
BROKER_EXECUTION_ENABLED=false
REQUIRE_HUMAN_APPROVAL=true
TRADIER_ENV=sandbox
ENABLE_TRADIER_SANDBOX_ORDERS=false
AUTONOMY_LEVEL=paper_trade
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
python -m app.main report performance
```

## JSONL Source Bridge

Sprint 2B does not log in to X directly. It watches a private JSONL file written by a bridge or manual helper:

```bash
python scripts/append_source_post.py \
  --post-id "2070159524963754262" \
  --url "https://x.com/stockoptions888/status/2070159524963754262" \
  --text '$HNI 45 CALL 7/17 avg .75'

python -m app.main run-once
python -m app.main alerts
python -m app.main paper
python -m app.main report performance
```

Default Docker path:

```env
SOURCE_JSONL_PATH=/app/input/source_posts.jsonl
```

The `/app/input` path should be backed by the named Docker volume `sniper_alert_input`.

## Manual Ingest Testing

```bash
python -m app.main ingest-manual --text '$HNI 45 CALL 7/17 avg .75'
python -m app.main alerts
python -m app.main audit
```

With `MARKET_DATA_PROVIDER=none`, quote-dependent alerts are scored as `needs_review`.

## Sprint 1 Acceptance Test

```bash
python -m app.main ingest-manual --text '$HNI 45 CALL 7/17 avg .75'
python -m app.main status
python -m app.main alerts
python -m app.main audit
python -m pytest
```

Expected result: Lux can run Sniper Alert on the VPS, process a manual alert, parse the contract, save it to SQLite, score it conservatively, mark it as `needs_review` when quote data is missing, and notify John privately.

## Sprint 2B Acceptance Test

```bash
python -m app.main status
python scripts/append_source_post.py --post-id "2070159524963754262" --url "https://x.com/stockoptions888/status/2070159524963754262" --text '$HNI 45 CALL 7/17 avg .75'
python -m app.main run-once
python -m app.main alerts
python -m app.main paper
python -m app.main audit
python -m app.main report performance
python -m pytest
```

Expected result: Sniper Alert ingests the JSONL source post, deduplicates it by `source_post_id`, parses the option contract, requests Tradier quote data only if credentials exist, scores missing quotes as `needs_review`, opens a local paper copy from the alert price in `paper_trade` mode, audits every step, and never submits a broker order.

## Tradier Path

Tradier is the selected future broker integration path. Sprint 2B keeps Tradier read-only and non-executing:

```env
BROKER_PROVIDER=tradier
BROKER_MODE=read_only
BROKER_EXECUTION_ENABLED=false
REQUIRE_HUMAN_APPROVAL=true
TRADIER_ENV=sandbox
ENABLE_TRADIER_SANDBOX_ORDERS=false
TRADIER_ACCESS_TOKEN=
TRADIER_SANDBOX_ACCESS_TOKEN=
TRADIER_LIVE_ACCESS_TOKEN=
TRADIER_ACCOUNT_ID=
```

No Tradier credentials are required. Missing credentials produce warnings and review-needed scoring, not crashes. No live orders are submitted. If `TRADIER_ENV=live`, order submission refuses to run.

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
        input volume: sniper_alert_input
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
9. Add Docker volumes for `/app/data`, `/app/logs`, and `/app/input`.
10. Add the safe environment variables below.
11. Save and deploy the new `sniper-alert` container.
12. Confirm both containers are running.
13. Check `sniper-alert` logs.

Safe Docker environment variables:

```env
APP_NAME=Sniper Alert
SOURCE_MODE=jsonl_watch
SOURCE_JSONL_PATH=/app/input/source_posts.jsonl
MARKET_DATA_PROVIDER=tradier
BROKER_PROVIDER=tradier
BROKER_MODE=read_only
BROKER_EXECUTION_ENABLED=false
REQUIRE_HUMAN_APPROVAL=true
TRADIER_ENV=sandbox
ENABLE_TRADIER_SANDBOX_ORDERS=false
AUTONOMY_LEVEL=paper_trade
PUBLIC_X_ENGAGEMENT=false
KILL_SWITCH=false
LLM_ENABLED=false
LLM_REQUIRED=false
NOTIFICATION_PROVIDER=telegram
ALLOW_MARKET_ORDERS=false
ALLOW_SHORT_OPTIONS=false
ALLOW_MULTI_LEG_OPTIONS=false
DATABASE_URL=sqlite:////app/data/sniper_alert.sqlite
LOG_FILE=/app/logs/sniper_alert.log
```

Terminal checks:

```bash
docker ps
docker exec sniper-alert printenv | grep -E "APP_NAME|SOURCE_MODE|SOURCE_JSONL|MARKET_DATA|LLM|TELEGRAM|BROKER|TRADIER|AUTONOMY|KILL_SWITCH"
docker logs sniper-alert --tail 100
```

Do not paste secret values into tickets, docs, or logs. The app status output only reports whether `OPENAI_API_KEY` is configured, not the value.

Before daemon mode, run these acceptance commands inside the `sniper-alert` container or app directory:

```bash
python -m app.main status
python scripts/append_source_post.py --post-id "2070159524963754262" --url "https://x.com/stockoptions888/status/2070159524963754262" --text '$HNI 45 CALL 7/17 avg .75'
python -m app.main run-once
python -m app.main alerts
python -m app.main paper
python -m app.main audit
python -m app.main report performance
```

Expected result: the `sniper-alert` container processes the JSONL alert, saves it to SQLite, scores missing quote data as `needs_review`, opens a local paper position from the alert price, and does not attempt any broker action. It does not require OpenAI, X, Tradier credentials, broker credentials, or live market data.

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

Claimed performance is stored separately and defaults to `not_enough_data`.

## Why No Live Trading Exists

Sniper Alert proves the core monitoring workflow before any execution discussion. The useful milestone is evidence: raw posts, parsed alerts, conservative scores, private notifications, paper tracking, and claimed-versus-verified performance. No code path places a real live trade in this repo, including Tradier.
