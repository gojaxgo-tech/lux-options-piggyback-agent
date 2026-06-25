from datetime import date, datetime, timezone

from app.models import AutonomyLevel, ControlState, MarketQuote, ScoreDecision
from app.parser import parse_first_alert
from app.scoring import EnterabilityScorer


def control(paused=False, kill_switch=False):
    return ControlState(paused=paused, kill_switch=kill_switch, autonomy_level=AutonomyLevel.MONITOR_ONLY)


def test_missing_quote_returns_needs_review():
    alert = parse_first_alert("$HNI 45 CALL 7/17 avg .75", today=date(2026, 6, 25))

    score = EnterabilityScorer().score(alert, None, control())

    assert score.decision == ScoreDecision.NEEDS_REVIEW
    assert "missing_quote" in score.reason_codes


def test_here_contract_missing_price_is_not_low_confidence():
    alert = parse_first_alert("$HNI 45 CALL 7/17 HERE", today=date(2026, 6, 25))

    score = EnterabilityScorer().score(alert, None, control())

    assert score.decision == ScoreDecision.NEEDS_REVIEW
    assert "valid_contract_missing_price" in score.reason_codes
    assert "contract_parse_low_confidence" not in score.reason_codes


def test_price_chased_returns_too_late():
    alert = parse_first_alert("$HNI 45 CALL 7/17 avg .75", today=date(2026, 6, 25))
    quote = MarketQuote("stub", datetime.now(timezone.utc), option_bid=1.10, option_ask=1.20, option_last=1.15, volume=100, open_interest=100)

    score = EnterabilityScorer(max_entry_slippage_pct=20).score(alert, quote, control())

    assert score.decision == ScoreDecision.TOO_LATE
    assert "do_not_chase" in score.reason_codes


def test_price_moved_moderately_returns_chased():
    alert = parse_first_alert("$HNI 45 CALL 7/17 avg .75", today=date(2026, 6, 25))
    quote = MarketQuote("stub", datetime.now(timezone.utc), option_bid=0.84, option_ask=0.88, option_last=0.86, volume=100, open_interest=100)

    score = EnterabilityScorer(max_entry_slippage_pct=20).score(alert, quote, control())

    assert score.decision == ScoreDecision.CHASED
    assert "price_moved_above_alert" in score.reason_codes
