from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.audit import AuditLogger, configure_disk_logging
from app.broker import build_broker
from app.config import load_settings
from app.database import Database
from app.health import HealthReporter
from app.llm.fallback import LlmFallback
from app.lux_agent import LuxAgent
from app.market_data import build_market_data_provider
from app.models import AutonomyLevel, MarketQuote
from app.notifications import build_notifier
from app.scoring import EnterabilityScorer
from app.service import run_forever
from app.social_provider import FileSocialProvider, XApiPlaceholderProvider


def build_agent():
    settings = load_settings()
    configure_disk_logging(settings.log_file, settings.log_level)
    database = Database(settings.db_path)
    database.initialize_control_state(settings.autonomy_level, settings.kill_switch)
    audit = AuditLogger(database)
    provider = (
        XApiPlaceholderProvider(settings.x_bearer_token)
        if settings.source_mode == "x_api"
        else FileSocialProvider(settings.source_posts_file, settings.source_platform, settings.source_account)
    )
    agent = LuxAgent(
        social_provider=provider,
        market_data_provider=build_market_data_provider(settings.market_data_provider),
        broker_provider=build_broker(settings),
        notifier=build_notifier(settings.notification_provider, settings.telegram_bot_token, settings.telegram_chat_id),
        scoring_engine=EnterabilityScorer(settings.max_entry_slippage_pct, settings.max_spread_pct),
        llm_fallback=LlmFallback(settings, audit),
        database=database,
        audit_logger=audit,
        settings=settings,
    )
    return settings, database, audit, agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Sniper Alert monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-once")
    sub.add_parser("daemon")
    sub.add_parser("run")
    sub.add_parser("status")
    sub.add_parser("pause")
    sub.add_parser("resume")
    kill = sub.add_parser("kill-switch")
    kill.add_argument("state", choices=("on", "off"))
    autonomy = sub.add_parser("autonomy")
    autonomy.add_argument("level", choices=[level.value for level in AutonomyLevel])
    sub.add_parser("health")
    sub.add_parser("logs")
    ingest = sub.add_parser("ingest-manual")
    ingest.add_argument("--text", required=True)
    quote = sub.add_parser("quote-manual")
    quote.add_argument("--alert-id", type=int, required=True)
    quote.add_argument("--bid", type=float)
    quote.add_argument("--ask", type=float)
    quote.add_argument("--last", type=float)
    sub.add_parser("alerts")
    sub.add_parser("paper")
    sub.add_parser("audit")

    args = parser.parse_args()
    settings, database, audit, agent = build_agent()

    if args.command in ("daemon", "run"):
        audit.log("daemon_loop_started", "Sniper Alert daemon loop started")
        run_forever(agent, settings.poll_interval_seconds)
    elif args.command == "run-once":
        audit.log("run_once_executed", "Run once executed")
        count = agent.run_scan_cycle()
        print(f"scan complete: {count} new posts")
    elif args.command == "status":
        print(_status(settings, database))
    elif args.command == "pause":
        database.set_paused(True)
        audit.log("pause_enabled", "Pause enabled")
        print("paused")
    elif args.command == "resume":
        database.set_paused(False)
        audit.log("pause_disabled", "Pause disabled")
        print("resumed")
    elif args.command == "kill-switch":
        enabled = args.state == "on"
        database.set_kill_switch(enabled)
        audit.log("kill_switch_enabled" if enabled else "kill_switch_disabled", f"Kill switch {args.state}", "warning" if enabled else "info")
        print(f"kill_switch={args.state}")
    elif args.command == "autonomy":
        level = AutonomyLevel(args.level)
        database.set_autonomy(level)
        audit.log("autonomy_changed", f"Autonomy changed to {level.value}")
        print(f"autonomy={level.value}")
    elif args.command == "health":
        checks = HealthReporter(database, settings).run()
        print("\n".join(f"{check.status}: {check.check_name} - {check.message}" for check in checks))
    elif args.command == "logs":
        print(_tail(settings.log_file))
    elif args.command == "ingest-manual":
        result = agent.ingest_manual(args.text)
        print(json.dumps(result, indent=2))
    elif args.command == "quote-manual":
        quote = MarketQuote(
            quote_source="manual",
            quote_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            option_bid=args.bid,
            option_ask=args.ask,
            option_last=args.last,
        )
        quote_id = database.save_quote(args.alert_id, quote)
        audit.log("manual_quote_added", f"Manual quote {quote_id} added for alert {args.alert_id}")
        print(f"quote_id={quote_id}")
    elif args.command == "alerts":
        print(_rows(database, """
            select
                parsed_alerts.id,
                parsed_alerts.ticker,
                parsed_alerts.option_type,
                parsed_alerts.strike,
                parsed_alerts.expiration_date,
                parsed_alerts.alert_price,
                parsed_alerts.needs_review as parse_needs_review,
                scores.decision as review_decision,
                scores.score,
                scores.reason_codes
            from parsed_alerts
            left join scores on scores.id = (
                select id from scores
                where scores.parsed_alert_id = parsed_alerts.id
                order by id desc
                limit 1
            )
            order by parsed_alerts.id desc
            limit 20
        """))
    elif args.command == "paper":
        print(_rows(database, "select id, parsed_alert_id, status, paper_entry_price, paper_pnl_percent, notes from paper_positions order by id desc limit 20"))
    elif args.command == "audit":
        print(_rows(database, "select id, event_type, severity, message, created_at from audit_events order by id desc limit 30"))


def _status(settings, database: Database) -> str:
    state = database.get_control_state()
    try:
        database.conn.execute("select 1").fetchone()
        db_state = "ok"
    except Exception:
        db_state = "error"
    return "\n".join(
        [
            "Sniper Alert status",
            f"database={db_state} path={settings.db_path}",
            f"paused={state.paused}",
            f"kill_switch={state.kill_switch}",
            f"autonomy={state.autonomy_level.value}",
            f"last_source_check_at={state.last_source_check_at}",
            f"last_successful_ingest_at={state.last_successful_ingest_at}",
            f"market_data_provider={settings.market_data_provider}",
            f"llm_enabled={settings.llm_enabled}",
            f"llm_required={settings.llm_required}",
            f"openai_api_key_configured={bool(settings.openai_api_key)}",
            f"broker_provider={settings.broker_provider}",
            f"broker_mode={settings.broker_mode}",
            f"broker_execution_enabled={settings.broker_execution_enabled}",
            f"require_human_approval={settings.require_human_approval}",
            f"tradier_env={settings.tradier_env}",
            f"public_x_engagement={settings.public_x_engagement}",
        ]
    )


def _tail(path: Path, line_count: int = 80) -> str:
    if not path.exists():
        return f"No log file at {path}"
    lines = path.read_text(errors="replace").splitlines()
    return "\n".join(lines[-line_count:])


def _rows(database: Database, query: str) -> str:
    rows = [dict(row) for row in database.conn.execute(query)]
    return json.dumps(rows, indent=2)


if __name__ == "__main__":
    main()
