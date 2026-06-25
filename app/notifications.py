from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Protocol

from app.models import MarketQuote, ParsedAlert, ScoreResult


class Notifier(Protocol):
    def send(self, subject: str, message: str) -> None:
        ...


class ConsoleNotifier:
    def send(self, subject: str, message: str) -> None:
        print(f"[{subject}]\n{message}")


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, subject: str, message: str) -> None:
        if not self.bot_token or not self.chat_id:
            raise RuntimeError("Telegram notifier is not configured")
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = urllib.parse.urlencode({"chat_id": self.chat_id, "text": f"{subject}\n\n{message}"}).encode()
        with urllib.request.urlopen(url, data=payload, timeout=10) as response:
            json.loads(response.read().decode())


def build_notifier(provider: str, telegram_bot_token: str, telegram_chat_id: str) -> Notifier:
    if provider == "telegram" and telegram_bot_token and telegram_chat_id:
        return TelegramNotifier(telegram_bot_token, telegram_chat_id)
    return ConsoleNotifier()


def format_alert_notification(source_account: str, alert: ParsedAlert, quote: MarketQuote | None, score: ScoreResult) -> str:
    quote_text = "missing"
    if quote:
        quote_text = f"bid={quote.option_bid} ask={quote.option_ask} last={quote.option_last}"
    return "\n".join(
        [
            "Sniper Alert",
            f"Source: @{source_account.lstrip('@')}",
            "Type: New Options Alert",
            f"Ticker: {alert.ticker or 'unknown'}",
            f"Contract: {alert.contract_symbol or 'needs review'}",
            f"Alert Price: {alert.alert_price if alert.alert_price is not None else 'missing'}",
            f"Current Quote: {quote_text}",
            f"Decision: {score.decision.value}",
            f"Score: {score.score}",
            f"Reason: {', '.join(score.reason_codes)}",
            f"Raw Post: {alert.raw_alert_text}",
            "Status: John review required" if score.decision.value != "paper_candidate" else "Status: Paper candidate only",
        ]
    )

