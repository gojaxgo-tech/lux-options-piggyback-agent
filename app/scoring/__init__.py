from __future__ import annotations

from datetime import datetime, timedelta, timezone, date

from app.models import ControlState, MarketQuote, ParsedAlert, ScoreDecision, ScoreResult


class EnterabilityScorer:
    def __init__(self, max_entry_slippage_pct: float = 20, max_spread_pct: float = 25, max_quote_age_minutes: int = 15):
        self.max_entry_slippage_pct = max_entry_slippage_pct
        self.max_spread_pct = max_spread_pct
        self.max_quote_age_minutes = max_quote_age_minutes

    def score(self, alert: ParsedAlert, quote: MarketQuote | None, control: ControlState) -> ScoreResult:
        if control.kill_switch:
            return ScoreResult(0, ScoreDecision.BLOCKED_BY_KILL_SWITCH, ("kill_switch_active",), "Kill switch is active.")
        if control.paused:
            return ScoreResult(0, ScoreDecision.PAUSED, ("paused",), "Sniper Alert is paused.")
        if alert.needs_review or not alert.ticker or not alert.option_type or not alert.strike or not alert.expiration_date:
            return ScoreResult(20, ScoreDecision.NEEDS_REVIEW, ("contract_parse_low_confidence",), "Contract parse needs review.")
        if quote is None or quote.option_mid is None:
            return ScoreResult(25, ScoreDecision.NEEDS_REVIEW, ("missing_quote",), "Missing option quote. John review required.")

        reason_codes: list[str] = []
        score = 60
        now = datetime.now(timezone.utc)
        quote_time = quote.quote_time if quote.quote_time.tzinfo else quote.quote_time.replace(tzinfo=timezone.utc)
        if now - quote_time > timedelta(minutes=self.max_quote_age_minutes):
            return ScoreResult(35, ScoreDecision.NEEDS_REVIEW, ("stale_quote",), "Quote is stale. John review required.")

        if alert.alert_price is not None and alert.alert_price > 0:
            current_entry = quote.option_ask if quote.option_ask is not None else quote.option_mid
            slippage_pct = ((current_entry - alert.alert_price) / alert.alert_price) * 100
            if slippage_pct > 25:
                return ScoreResult(30, ScoreDecision.TOO_LATE, ("do_not_chase",), f"Option moved {slippage_pct:.1f}% above alert price.")
            if slippage_pct > 10:
                return ScoreResult(45, ScoreDecision.CHASED, ("price_moved_above_alert",), f"Option moved {slippage_pct:.1f}% above alert price.")
            score += 15
            reason_codes.append("price_near_alert")

        if quote.option_bid is not None and quote.option_ask is not None and quote.option_mid:
            spread_pct = ((quote.option_ask - quote.option_bid) / quote.option_mid) * 100
            if spread_pct > self.max_spread_pct:
                return ScoreResult(40, ScoreDecision.BAD_SPREAD, ("wide_spread",), f"Bid/ask spread is wide at {spread_pct:.1f}%.")

        if alert.expiration_date:
            try:
                dte = (date.fromisoformat(alert.expiration_date) - date.today()).days
                if dte <= 7:
                    return ScoreResult(35, ScoreDecision.NEEDS_REVIEW, ("high_time_decay_risk",), "Expiration is within 7 days.")
            except ValueError:
                pass

        if quote.volume is None:
            score -= 5
            reason_codes.append("low_volume")
        elif quote.volume >= 100:
            score += 5

        if quote.open_interest is None:
            score -= 5
            reason_codes.append("missing_open_interest")
        elif quote.open_interest >= 100:
            score += 5

        reason_codes.append("fresh_alert")
        score = max(0, min(100, score))
        decision = ScoreDecision.PAPER_CANDIDATE if score >= 70 else ScoreDecision.NEAR_ALERT_PRICE if "price_near_alert" in reason_codes else ScoreDecision.WATCH
        summary = "Conservative paper candidate." if decision == ScoreDecision.PAPER_CANDIDATE else "Watch only; John review recommended."
        return ScoreResult(score, decision, tuple(reason_codes), summary)


ScoringEngine = EnterabilityScorer
