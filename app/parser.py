from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from app.models import OptionType, ParsedAlert, TradeUpdate


CONTRACT_RE = re.compile(
    r"""
    \$?(?P<ticker>[A-Z]{1,6})\s+
    (?P<strike>\d+(?:\.\d+)?)\s+
    (?P<option_type>CALL|PUT|C|P)\s+
    (?P<expiration>\d{1,2}/\d{1,2}(?:/\d{2,4})?)
    (?P<trailing>[\s\S]*?)(?=(?:\$?[A-Z]{1,6}\s+\d+(?:\.\d+)?\s+(?:CALL|PUT|C|P)\s+\d{1,2}/\d{1,2})|$)
    """,
    re.IGNORECASE | re.VERBOSE,
)
PRICE_RE = re.compile(r"\b(?:avg|average|entry|at|@)\s*\$?(?P<price>(?:\d+)?\.\d+|\d+(?:\.\d+)?)", re.IGNORECASE)
CLAIM_PRICE_RE = re.compile(r"\$?(?P<price>\d+(?:\.\d+)?)\s+on\s+\$?(?P<ticker>[A-Z]{1,6})", re.IGNORECASE)
CLAIM_GAIN_RE = re.compile(r"(?P<gain>\d+(?:\.\d+)?)\s*%", re.IGNORECASE)


def parse_alerts(text: str, today: date | None = None) -> list[ParsedAlert]:
    today = today or date.today()
    normalized = " ".join(text.split())
    alerts: list[ParsedAlert] = []
    for match in CONTRACT_RE.finditer(normalized):
        alerts.append(_alert_from_match(normalized, match, today))
    if alerts:
        return alerts
    return [
        ParsedAlert(
            raw_alert_text=normalized,
            parse_confidence=0.0,
            needs_review=True,
        )
    ]


def parse_first_alert(text: str, today: date | None = None) -> ParsedAlert:
    return parse_alerts(text, today)[0]


def parse_trade_update(text: str) -> TradeUpdate:
    normalized = " ".join(text.split())
    price_match = CLAIM_PRICE_RE.search(normalized)
    gain_match = CLAIM_GAIN_RE.search(normalized)
    update_type = "claimed_result" if price_match or gain_match else "trade_update"
    status = "unverified_claim" if update_type == "claimed_result" else None
    return TradeUpdate(
        update_type=update_type,
        raw_update_text=normalized,
        ticker=price_match.group("ticker").upper() if price_match else _first_ticker(normalized),
        claimed_price=_parse_price(price_match.group("price")) if price_match else None,
        claimed_percent_gain=float(gain_match.group("gain")) if gain_match else None,
        claimed_status=status,
    )


def _alert_from_match(raw_text: str, match: re.Match, today: date) -> ParsedAlert:
    option_raw = match.group("option_type").upper()
    option_type = OptionType.CALL if option_raw in ("CALL", "C") else OptionType.PUT
    expiration, inferred = _resolve_expiration(match.group("expiration"), today)
    trailing = match.group("trailing") or ""
    price_match = PRICE_RE.search(trailing)
    alert_price_raw = price_match.group("price") if price_match else None
    alert_price = _parse_price(alert_price_raw) if alert_price_raw else None
    confidence_label = _first_present(raw_text, ("HIGH CONFIDENCE",))
    hype_label = _first_present(raw_text, ("700% POTENTIAL", "LOTTO", "STARTER"))
    time_horizon = _first_present(raw_text, ("SWING OVERNIGHT", "OVERNIGHT", "SWING", "SCALP"))
    fields_present = [
        bool(match.group("ticker")),
        bool(match.group("strike")),
        bool(option_type),
        bool(expiration),
        alert_price is not None or "HERE" in trailing.upper(),
    ]
    parse_confidence = sum(1 for item in fields_present if item) / len(fields_present)
    inferred_fields = ("expiration_year",) if inferred else ()
    ticker = match.group("ticker").upper()
    strike = float(match.group("strike"))
    contract_symbol = f"{ticker} {strike:g} {option_type.value} {match.group('expiration')}"
    return ParsedAlert(
        raw_alert_text=raw_text,
        ticker=ticker,
        option_type=option_type,
        strike=strike,
        expiration_date=expiration,
        alert_price=alert_price,
        alert_price_raw=alert_price_raw,
        contract_symbol=contract_symbol,
        side="long",
        strategy="options_signal_follow",
        time_horizon=time_horizon,
        confidence_label=confidence_label,
        hype_label=hype_label,
        parse_confidence=parse_confidence,
        needs_review=parse_confidence < 0.8 or alert_price is None,
        inferred_fields=inferred_fields,
    )


def _parse_price(raw: str | None) -> float | None:
    if raw is None:
        return None
    if raw.startswith("."):
        raw = "0" + raw
    return float(raw)


def _resolve_expiration(raw: str, today: date) -> tuple[str, bool]:
    parts = [int(part) for part in raw.split("/")]
    if len(parts) == 3:
        year = parts[2]
        if year < 100:
            year += 2000
        return date(year, parts[0], parts[1]).isoformat(), False
    month, day = parts
    year = today.year
    resolved = date(year, month, day)
    if resolved < today:
        resolved = date(year + 1, month, day)
    return resolved.isoformat(), True


def _first_present(text: str, candidates: Iterable[str]) -> str | None:
    upper = text.upper()
    for candidate in candidates:
        if candidate in upper:
            return candidate
    return None


def _first_ticker(text: str) -> str | None:
    match = re.search(r"\$([A-Z]{1,6})\b", text)
    return match.group(1).upper() if match else None

