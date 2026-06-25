from __future__ import annotations

from app.models import MarketQuote, ParsedAlert


class PaperTracker:
    def __init__(self, database):
        self.database = database

    def maybe_open(self, parsed_alert_id: int, alert: ParsedAlert, quote: MarketQuote | None, enabled: bool) -> bool:
        if not enabled:
            return False
        if quote is None or quote.option_mid is None:
            return False
        self.database.create_paper_position(parsed_alert_id, quote.option_mid, "entry based on quote mid")
        return True


PaperTrader = PaperTracker

