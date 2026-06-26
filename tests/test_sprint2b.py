import json
from datetime import datetime, timezone

from app.audit import AuditLogger
from app.broker import build_broker
from app.classifier import classify_text
from app.database import Database
from app.market_data import TradierMarketDataProvider
from app.models import AutonomyLevel, Classification, SocialPost
from app.notifications import format_alert_notification, format_claim_notification
from app.paper_trading import PaperTracker
from app.parser import parse_alerts
from app.reports import ReportGenerator
from app.scoring import EnterabilityScorer
from app.config import Settings
from app.social_provider import JsonlSourceProvider
from app.trades import canonical_trade_id, state_hash


def settings(tmp_path):
    return Settings(
        app_name="Sniper Alert",
        app_env="test",
        timezone="America/Los_Angeles",
        database_url=f"sqlite:///{tmp_path / 'sniper.sqlite'}",
        db_path=tmp_path / "sniper.sqlite",
        log_level="INFO",
        log_file=tmp_path / "sniper.log",
        source_platform="x",
        source_account="StockOptions888",
        source_mode="jsonl_watch",
        source_jsonl_path=tmp_path / "source_posts.jsonl",
        x_bearer_token="",
        notification_provider="console",
        telegram_bot_token="",
        telegram_chat_id="",
        llm_enabled=False,
        llm_required=False,
        llm_provider="openai",
        openai_api_key="",
        llm_model_fast="gpt-5.4-nano",
        llm_model_review="gpt-5.4-mini",
        llm_model_deep="gpt-5.5",
        llm_use_deep=False,
        llm_max_calls_per_day=200,
        llm_calls_only_on_low_confidence=True,
        market_data_provider="tradier",
        broker_provider="tradier",
        broker_mode="read_only",
        autonomy_level=AutonomyLevel.PAPER_TRADE,
        broker_execution_enabled=False,
        require_human_approval=True,
        tradier_env="sandbox",
        tradier_access_token="",
        tradier_sandbox_access_token="",
        tradier_live_access_token="",
        tradier_account_id="",
        tradier_base_url_sandbox="https://sandbox.tradier.com/v1",
        tradier_base_url_live="https://api.tradier.com/v1",
        enable_tradier_sandbox_orders=False,
        allow_market_orders=False,
        allow_short_options=False,
        allow_multi_leg_options=False,
        public_x_engagement=False,
        kill_switch=False,
        poll_interval_seconds=60,
        stale_source_warning_minutes=30,
        max_entry_slippage_pct=20,
        max_spread_pct=25,
        source_posts_file=None,
    )


def test_jsonl_provider_ingests_invalid_and_duplicate_lines(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    audit = AuditLogger(db)
    path = tmp_path / "source_posts.jsonl"
    payload = {
        "source_platform": "x",
        "source_account": "StockOptions888",
        "source_post_id": "2070159524963754262",
        "source_url": "https://x.com/stockoptions888/status/2070159524963754262",
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "raw_text": "$HNI 45 CALL 7/17 avg .75",
    }
    path.write_text(json.dumps(payload) + "\nnot-json\n" + json.dumps(payload) + "\n")

    posts = JsonlSourceProvider(path, "x", "StockOptions888", audit).fetch_new_posts(set())

    assert len(posts) == 1
    events = [row["event_type"] for row in db.conn.execute("select event_type from audit_events")]
    assert "jsonl_line_ingested" in events
    assert "jsonl_line_invalid" in events
    assert "jsonl_duplicate_skipped" in events


def test_exit_language_classifies_and_marks_source_exit(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    alert_post = SocialPost("x", "StockOptions888", "1", "$HNI 45 CALL 7/17 avg .75", datetime.now(timezone.utc))
    social_id, _ = db.save_social_post(alert_post)
    parsed_id = db.save_parsed_alert(social_id, parse_alerts(alert_post.raw_text)[0])
    db.create_paper_position(parsed_id, 0.75, "paper copy", "alert_price")

    update_post = SocialPost("x", "StockOptions888", "2", "$HNI sold half, leave runners", datetime.now(timezone.utc))
    update_id, _ = db.save_social_post(update_post)
    assert classify_text(update_post.raw_text).classification == Classification.TRIM_UPDATE
    from app.parser import parse_trade_update

    db.save_trade_update(update_id, parse_trade_update(update_post.raw_text))

    row = db.conn.execute("select status, source_exit_detected from paper_positions").fetchone()
    assert row["status"] == "source_exit_detected"
    assert row["source_exit_detected"] == 1


def test_paper_position_uses_alert_price_when_quote_missing(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    post = SocialPost("x", "StockOptions888", "1", "$HNI 45 CALL 7/17 avg .75", datetime.now(timezone.utc))
    social_id, _ = db.save_social_post(post)
    alert = parse_alerts(post.raw_text)[0]
    parsed_id = db.save_parsed_alert(social_id, alert)

    opened = PaperTracker(db).maybe_open(parsed_id, alert, None, enabled=True)

    row = db.conn.execute("select paper_entry_price, paper_entry_source, ticker from paper_positions").fetchone()
    assert opened is True
    assert row["paper_entry_price"] == 0.75
    assert row["paper_entry_source"] == "alert_price"
    assert row["ticker"] == "HNI"


def test_performance_report_and_notifications(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    audit = AuditLogger(db)
    report = json.loads(ReportGenerator(db, audit).performance())

    assert "source_claimed_performance" in report
    assert "local_paper_performance" in report
    assert "tradier_sandbox_performance" in report
    assert "Options are high risk" in format_alert_notification("StockOptions888", parse_alerts("$HNI 45 CALL 7/17 avg .75")[0], None, EnterabilityScorer().score(parse_alerts("$HNI 45 CALL 7/17 avg .75")[0], None, db.get_control_state()))
    assert "Claimed results are not counted" in format_claim_notification("StockOptions888", "Winner banked 100%", "not_enough_data")


def test_source_quality_report_uses_locked_rubric(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    audit = AuditLogger(db)
    clean_post = SocialPost("x", "StockOptions888", "1", "HIGH CONFIDENCE 🔥🚨\n\n$MTUS 22.5 CALL 7/17 avg .20🚨", datetime.now(timezone.utc))
    missing_price_post = SocialPost("x", "StockOptions888", "2", "Overnight swing\n\n$HNI 45 CALL 7/17 HERE🚨", datetime.now(timezone.utc))
    hype_post = SocialPost("x", "StockOptions888", "3", "1000% POTENTIAL 🔥🚨\n\n$MTUS 22.5 CALL 7/17 HERE🚨", datetime.now(timezone.utc))
    for post in (clean_post, missing_price_post, hype_post):
        social_id, _ = db.save_social_post(post)
        db.update_classification(social_id, classify_text(post.raw_text))
        db.save_parsed_alert(social_id, parse_alerts(post.raw_text)[0])

    report = json.loads(ReportGenerator(db, audit).source_quality())

    assert report["clean_priced_entries"] == 1
    assert report["valid_missing_price_entries"] == 2
    assert report["hype_potential_posts"] == 1
    assert report["parser_misses"] == 0


def test_tradier_missing_credentials_and_order_safety(tmp_path):
    cfg = settings(tmp_path)
    db = Database(tmp_path / "sniper.sqlite")
    audit = AuditLogger(db)
    provider = TradierMarketDataProvider(cfg, audit)

    assert provider.configured() is False
    assert provider.get_option_quote(parse_alerts("$HNI 45 CALL 7/17 avg .75")[0]) is None
    assert build_broker(cfg).submit_sandbox_paper_order()["status"] == "disabled"


def test_tradier_live_mode_refuses_sandbox_order(tmp_path):
    cfg = settings(tmp_path)
    live_cfg = Settings(**{**cfg.__dict__, "tradier_env": "live", "enable_tradier_sandbox_orders": True})

    try:
        build_broker(live_cfg).submit_sandbox_paper_order()
    except RuntimeError as exc:
        assert "outside sandbox" in str(exc)
    else:
        raise AssertionError("live mode should refuse sandbox paper orders")


def test_paper_threshold_crossing_is_audited(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    audit = AuditLogger(db)
    post = SocialPost("x", "StockOptions888", "1", "$HNI 45 CALL 7/17 avg .75", datetime.now(timezone.utc))
    social_id, _ = db.save_social_post(post)
    alert = parse_alerts(post.raw_text)[0]
    parsed_id = db.save_parsed_alert(social_id, alert)
    tracker = PaperTracker(db)
    tracker.maybe_open(parsed_id, alert, None, enabled=True)

    crossed = tracker.update_price(parsed_id, 1.13, audit)

    assert 50 in crossed
    events = [row["event_type"] for row in db.conn.execute("select event_type from audit_events")]
    assert "paper_position_updated" in events
    assert "paper_threshold_crossed" in events


def test_canonical_trade_id_generation_and_expiration_normalization():
    alert = parse_alerts("$MTUS 22.5 CALL 7/17 avg .20")[0]

    assert alert.expiration_date.endswith("-07-17")
    assert canonical_trade_id(alert).endswith("_22_5C")


def test_duplicate_alerts_share_canonical_trade(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    first_post = SocialPost("x", "StockOptions888", "1", "$HNI 45 CALL 7/17 avg .75", datetime.now(timezone.utc))
    second_post = SocialPost("x", "StockOptions888", "2", "SWING OVERNIGHT $HNI 45 CALL 7/17 HERE", datetime.now(timezone.utc))
    ids = []
    for post in (first_post, second_post):
        social_id, _ = db.save_social_post(post)
        ids.append(db.save_parsed_alert(social_id, parse_alerts(post.raw_text)[0]))

    rows = [row["canonical_trade_id"] for row in db.conn.execute("select canonical_trade_id from parsed_alerts order by id")]
    trades = db.conn.execute("select count(*) as c from trades").fetchone()["c"]
    assert rows[0] == rows[1] == "HNI_2026_07_17_45C"
    assert trades == 1


def test_lifecycle_transitions_and_notification_dedupe(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    post = SocialPost("x", "StockOptions888", "1", "$HNI 45 CALL 7/17 avg .75", datetime.now(timezone.utc))
    social_id, _ = db.save_social_post(post)
    alert = parse_alerts(post.raw_text)[0]
    parsed_id = db.save_parsed_alert(social_id, alert)
    PaperTracker(db).maybe_open(parsed_id, alert, None, enabled=True)
    trade = db.conn.execute("select lifecycle_state from trades where canonical_trade_id = 'HNI_2026_07_17_45C'").fetchone()
    digest = state_hash("HNI_2026_07_17_45C", "new_clean_entry", "1", "needs_review")

    assert trade["lifecycle_state"] == "paper_open"
    assert db.should_notify("HNI_2026_07_17_45C", "new_clean_entry", "1", digest) is True
    assert db.should_notify("HNI_2026_07_17_45C", "new_clean_entry", "1", digest) is False


def test_latest_report_is_db_backed(tmp_path):
    db = Database(tmp_path / "sniper.sqlite")
    audit = AuditLogger(db)
    post = SocialPost("x", "StockOptions888", "1", "$HNI 45 CALL 7/17 avg .75", datetime.now(timezone.utc))
    social_id, _ = db.save_social_post(post)
    db.update_classification(social_id, classify_text(post.raw_text))
    db.save_parsed_alert(social_id, parse_alerts(post.raw_text)[0])

    report = json.loads(ReportGenerator(db, audit).latest())

    assert report["latest_source_posts"][0]["source_post_id"] == "1"
    assert report["latest_canonical_trades"][0]["canonical_trade_id"] == "HNI_2026_07_17_45C"
    assert "source_quality_summary" in report
