from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
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


class TradierMarketDataProvider:
    def __init__(self, settings, audit_logger=None):
        self.settings = settings
        self.audit_logger = audit_logger
        self.token = settings.tradier_sandbox_access_token if settings.tradier_env == "sandbox" else settings.tradier_live_access_token
        if not self.token:
            self.token = settings.tradier_access_token
        self.base_url = settings.tradier_base_url_sandbox if settings.tradier_env == "sandbox" else settings.tradier_base_url_live

    def configured(self) -> bool:
        return bool(self.token)

    def get_option_quote(self, alert: ParsedAlert) -> MarketQuote | None:
        if not self.configured() or not alert.ticker:
            if self.audit_logger:
                self.audit_logger.log("tradier_quote_failed", "Tradier credentials missing; quote unavailable", "warning")
            return None
        symbol = self.resolve_option_symbol(alert)
        if self.audit_logger:
            self.audit_logger.log("tradier_quote_requested", f"Tradier quote requested for {alert.contract_symbol}")
        if not symbol:
            if self.audit_logger:
                self.audit_logger.log("tradier_quote_failed", "Option symbol resolution failed; quote unavailable", "warning")
            return None
        try:
            payload = self._get("/markets/quotes", {"symbols": symbol, "greeks": "false"})
            quote_payload = payload.get("quotes", {}).get("quote")
            if isinstance(quote_payload, list):
                quote_payload = quote_payload[0] if quote_payload else None
            if not quote_payload:
                if self.audit_logger:
                    self.audit_logger.log("tradier_quote_failed", f"Tradier returned no quote for {symbol}", "warning")
                return None
            quote = MarketQuote(
                quote_source="tradier",
                quote_time=datetime.now(timezone.utc),
                option_bid=_as_float(quote_payload.get("bid")),
                option_ask=_as_float(quote_payload.get("ask")),
                option_last=_as_float(quote_payload.get("last")),
                volume=_as_int(quote_payload.get("volume")),
                open_interest=_as_int(quote_payload.get("open_interest")),
                raw_json=json.dumps(quote_payload),
            )
            if self.audit_logger:
                self.audit_logger.log("tradier_quote_received", f"Tradier quote received for {symbol}")
            return quote
        except Exception as exc:
            if self.audit_logger:
                self.audit_logger.log("tradier_quote_failed", f"Tradier quote failed: {exc}", "warning")
            return None

    def get_account_status(self) -> dict:
        return {"provider": "tradier", "env": self.settings.tradier_env, "configured": self.configured(), "mode": "read_only"}

    def get_balances(self) -> dict:
        if not self.settings.tradier_account_id:
            return {"status": "missing_account_id"}
        return self._get(f"/accounts/{self.settings.tradier_account_id}/balances")

    def get_positions(self) -> dict:
        if not self.settings.tradier_account_id:
            return {"status": "missing_account_id"}
        return self._get(f"/accounts/{self.settings.tradier_account_id}/positions")

    def get_underlying_quote(self, ticker: str) -> dict:
        return self._get("/markets/quotes", {"symbols": ticker.upper()})

    def get_option_chain(self, ticker: str, expiration: str) -> dict:
        return self._get("/markets/options/chains", {"symbol": ticker.upper(), "expiration": expiration, "greeks": "false"})

    def resolve_option_symbol(self, alert: ParsedAlert) -> str | None:
        if not alert.ticker or not alert.expiration_date or not alert.option_type or alert.strike is None:
            return None
        expiration = datetime.fromisoformat(alert.expiration_date).strftime("%y%m%d")
        strike = f"{int(round(alert.strike * 1000)):08d}"
        return f"{alert.ticker.upper():<6}{expiration}{alert.option_type.value[0]}{strike}"

    def _get(self, path: str, params: dict | None = None) -> dict:
        if not self.configured():
            raise RuntimeError("Tradier credentials missing")
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        request = urllib.request.Request(
            f"{self.base_url}{path}{query}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())


def _as_float(value) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _as_int(value) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def build_market_data_provider(settings_or_mode, audit_logger=None) -> MarketDataProvider:
    mode = settings_or_mode.market_data_provider if hasattr(settings_or_mode, "market_data_provider") else settings_or_mode
    if mode == "stub":
        return StubMarketDataProvider()
    if mode == "tradier":
        return TradierMarketDataProvider(settings_or_mode, audit_logger)
    return NoneMarketDataProvider()


NullMarketDataProvider = NoneMarketDataProvider
