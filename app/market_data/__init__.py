from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.models import MarketQuote, ParsedAlert


class MarketDataProvider(Protocol):
    def get_option_quote(self, alert: ParsedAlert) -> MarketQuote | None:
        ...


class NoneMarketDataProvider:
    def get_option_quote(self, alert: ParsedAlert) -> MarketQuote | None:
        return None


class StubMarketDataProvider:
    def get_option_quote(self, alert: ParsedAlert) -> MarketQuote | None:
        if alert.alert_price is None:
            return None
        bid = round(alert.alert_price * 0.95, 2)
        ask = round(alert.alert_price * 1.05, 2)
        return MarketQuote(
            quote_source="stub",
            quote_time=datetime.now(timezone.utc),
            option_bid=bid,
            option_ask=ask,
            option_last=alert.alert_price,
            volume=100,
            open_interest=100,
        )


def build_market_data_provider(mode: str) -> MarketDataProvider:
    if mode == "stub":
        return StubMarketDataProvider()
    return NoneMarketDataProvider()


NullMarketDataProvider = NoneMarketDataProvider
