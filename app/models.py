from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Classification(str, Enum):
    NEW_TRADE_ALERT = "new_trade_alert"
    TRADE_UPDATE = "trade_update"
    SOURCE_EXIT_UPDATE = "source_exit_update"
    CLAIMED_RESULT = "claimed_result"
    GENERAL_MARKET_COMMENTARY = "general_market_commentary"
    NON_TRADE = "non_trade"
    UNKNOWN = "unknown"


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class AutonomyLevel(str, Enum):
    MONITOR_ONLY = "monitor_only"
    PAPER_TRADE = "paper_trade"


class ScoreDecision(str, Enum):
    WATCH = "watch"
    NEEDS_REVIEW = "needs_review"
    NEAR_ALERT_PRICE = "near_alert_price"
    CHASED = "chased"
    TOO_LATE = "too_late"
    BAD_SPREAD = "bad_spread"
    STALE_ALERT = "stale_alert"
    PAPER_CANDIDATE = "paper_candidate"
    SKIP = "skip"
    INVALID = "invalid"
    BLOCKED_BY_KILL_SWITCH = "blocked_by_kill_switch"
    PAUSED = "paused"


@dataclass(frozen=True)
class SocialPost:
    source_platform: str
    source_account: str
    source_post_id: str
    raw_text: str
    posted_at: datetime
    source_url: Optional[str] = None
    raw_json: Optional[str] = None


@dataclass(frozen=True)
class ClassificationResult:
    classification: Classification
    confidence: float
    reason: str


@dataclass(frozen=True)
class ParsedAlert:
    raw_alert_text: str
    ticker: Optional[str] = None
    option_type: Optional[OptionType] = None
    strike: Optional[float] = None
    expiration_date: Optional[str] = None
    alert_price: Optional[float] = None
    alert_price_raw: Optional[str] = None
    contract_symbol: Optional[str] = None
    side: Optional[str] = "long"
    strategy: Optional[str] = None
    time_horizon: Optional[str] = None
    confidence_label: Optional[str] = None
    hype_label: Optional[str] = None
    parse_confidence: float = 0.0
    needs_review: bool = True
    inferred_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeUpdate:
    update_type: str
    raw_update_text: str
    ticker: Optional[str] = None
    claimed_price: Optional[float] = None
    claimed_percent_gain: Optional[float] = None
    claimed_status: Optional[str] = None
    source_exit_detected: bool = False


@dataclass(frozen=True)
class MarketQuote:
    quote_source: str
    quote_time: datetime
    option_bid: Optional[float] = None
    option_ask: Optional[float] = None
    option_last: Optional[float] = None
    underlying_price: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    iv: Optional[float] = None
    raw_json: Optional[str] = None

    @property
    def option_mid(self) -> Optional[float]:
        if self.option_bid is not None and self.option_ask is not None:
            return round((self.option_bid + self.option_ask) / 2, 4)
        return self.option_last


@dataclass(frozen=True)
class ScoreResult:
    score: int
    decision: ScoreDecision
    reason_codes: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class ControlState:
    paused: bool
    kill_switch: bool
    autonomy_level: AutonomyLevel
    last_source_check_at: Optional[str] = None
    last_successful_ingest_at: Optional[str] = None
