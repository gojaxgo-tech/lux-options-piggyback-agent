from pathlib import Path

from app.audit import AuditLogger
from app.broker import build_broker
from app.config import Settings
from app.database import Database
from app.llm.fallback import LlmFallback
from app.lux_agent import LuxAgent
from app.market_data import NoneMarketDataProvider
from app.models import AutonomyLevel
from app.notifications import ConsoleNotifier
from app.scoring import EnterabilityScorer
from app.social_provider import FileSocialProvider


def test_manual_ingest_persists_raw_alert_score_and_audit(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    db.initialize_control_state(AutonomyLevel.MONITOR_ONLY, False)
    settings = Settings(
        app_name="Sniper Alert",
        app_env="test",
        timezone="America/Los_Angeles",
        database_url=f"sqlite:///{tmp_path / 'sniper.sqlite'}",
        db_path=tmp_path / "sniper.sqlite",
        log_level="INFO",
        log_file=tmp_path / "sniper.log",
        source_platform="x",
        source_account="StockOptions888",
        source_mode="manual",
        x_bearer_token="",
        notification_provider="console",
        telegram_bot_token="",
        telegram_chat_id="",
        llm_enabled=True,
        llm_required=False,
        llm_provider="openai",
        openai_api_key="",
        llm_model_fast="gpt-5.4-nano",
        llm_model_review="gpt-5.4-mini",
        llm_model_deep="gpt-5.5",
        llm_use_deep=False,
        llm_max_calls_per_day=200,
        llm_calls_only_on_low_confidence=True,
        market_data_provider="none",
        broker_provider="tradier",
        broker_mode="none",
        autonomy_level=AutonomyLevel.MONITOR_ONLY,
        broker_execution_enabled=False,
        require_human_approval=True,
        tradier_env="sandbox",
        tradier_access_token="",
        tradier_account_id="",
        public_x_engagement=False,
        kill_switch=False,
        poll_interval_seconds=60,
        stale_source_warning_minutes=30,
        max_entry_slippage_pct=20,
        max_spread_pct=25,
        source_posts_file=None,
    )
    agent = LuxAgent(
        social_provider=FileSocialProvider(None, "x", "StockOptions888"),
        market_data_provider=NoneMarketDataProvider(),
        broker_provider=build_broker(settings),
        notifier=ConsoleNotifier(),
        scoring_engine=EnterabilityScorer(),
        llm_fallback=LlmFallback(settings, AuditLogger(db)),
        database=db,
        audit_logger=AuditLogger(db),
        settings=settings,
    )

    result = agent.ingest_manual("$HNI 45 CALL 7/17 avg .75")

    assert result["status"] == "processed"
    assert db.conn.execute("select count(*) as c from social_posts").fetchone()["c"] == 1
    assert db.conn.execute("select count(*) as c from parsed_alerts").fetchone()["c"] == 1
    assert db.conn.execute("select decision from scores").fetchone()["decision"] == "needs_review"
    assert db.conn.execute("select count(*) as c from audit_events").fetchone()["c"] > 0
