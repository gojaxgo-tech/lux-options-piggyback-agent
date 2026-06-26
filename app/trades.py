from __future__ import annotations

import hashlib

from app.models import ParsedAlert


def canonical_trade_id(alert: ParsedAlert) -> str | None:
    if not alert.ticker or not alert.expiration_date or not alert.option_type or alert.strike is None:
        return None
    expiration = alert.expiration_date.replace("-", "_")
    strike = _format_strike(alert.strike)
    return f"{alert.ticker.upper()}_{expiration}_{strike}{alert.option_type.value[0]}"


def state_hash(*parts: object) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _format_strike(strike: float) -> str:
    if float(strike).is_integer():
        return str(int(strike))
    return str(strike).rstrip("0").rstrip(".").replace(".", "_")
