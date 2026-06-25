from __future__ import annotations

from app.models import MarketQuote, ParsedAlert


class PaperTracker:
    def __init__(self, database):
        self.database = database

    def maybe_open(self, parsed_alert_id: int, alert: ParsedAlert, quote: MarketQuote | None, enabled: bool) -> bool:
        if not enabled:
            return False
        if self.database.paper_position_exists(parsed_alert_id):
            return False
        entry_source = "alert_price"
        entry_price = alert.alert_price
        if quote and quote.option_ask is not None:
            entry_price = quote.option_ask
            entry_source = "quote_ask"
        elif quote and quote.option_mid is not None:
            entry_price = quote.option_mid
            entry_source = "quote_mid"
        if entry_price is None:
            return False
        self.database.create_paper_position(parsed_alert_id, entry_price, f"paper copy entry based on {entry_source}", entry_source)
        return True

    def update_price(self, parsed_alert_id: int, last_price: float, audit_logger=None) -> list[int]:
        crossed = self.database.update_paper_position_price(parsed_alert_id, last_price)
        if audit_logger:
            audit_logger.log("paper_position_updated", f"Paper position {parsed_alert_id} updated to {last_price}")
            for threshold in crossed:
                audit_logger.log("paper_threshold_crossed", f"Paper position {parsed_alert_id} crossed {threshold}%")
        return crossed


PaperTrader = PaperTracker
