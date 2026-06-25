from __future__ import annotations

import json


class ReportGenerator:
    def __init__(self, database, audit_logger=None):
        self.database = database
        self.audit_logger = audit_logger

    def performance(self) -> str:
        data = self.database.performance_summary()
        if self.audit_logger:
            self.audit_logger.log("performance_report_generated", "Performance report generated")
        return json.dumps(
            {
                "source_claimed_performance": {
                    "source_claims": data["source_claims"],
                    "claims_verified": data["claims_verified"],
                    "claims_contradicted": data["claims_contradicted"],
                    "claims_not_enough_data": data["claims_not_enough_data"],
                },
                "local_paper_performance": data,
                "tradier_sandbox_performance": {"status": "not_enabled"},
                "verified_market_performance": {"status": "not_enough_data"},
                "unknown_or_insufficient_data": data["insufficient_data"],
            },
            indent=2,
        )

    def daily(self) -> str:
        return self.performance()

    def source_quality(self) -> str:
        data = self.database.performance_summary()
        if self.audit_logger:
            self.audit_logger.log("performance_report_generated", "Source quality report generated")
        conclusion = "insufficient data"
        if data["clean_priced_entries"] and data["claims_not_enough_data"]:
            conclusion = "promising but unverified"
        if data["hype_potential_posts"] > data["clean_priced_entries"]:
            conclusion = "hype-heavy"
        if data["alerts_skipped_missing_quote"]:
            conclusion = "improving with quote data needed"
        return json.dumps(
            {
                "total_source_posts_captured": data["total_source_posts"],
                "clean_priced_entries": data["clean_priced_entries"],
                "valid_missing_price_entries": data["valid_missing_price_entries"],
                "add_updates": data["add_updates"],
                "hold_watch_updates": data["hold_updates"],
                "trim_updates": data["trim_updates"],
                "full_exits": data["full_exits"],
                "claimed_results": data["source_claims"],
                "hype_potential_posts": data["hype_potential_posts"],
                "general_commentary": data["general_commentary"],
                "ambiguous_posts": data["ambiguous_posts"],
                "parser_misses": data["parser_misses"],
                "paper_positions_opened": data["paper_copied_alerts"],
                "open_paper_positions": data["open_paper_positions"],
                "closed_paper_positions": data["closed_paper_positions"],
                "claimed_wins_verified": data["claims_verified"],
                "claimed_wins_unverified": data["claims_not_enough_data"],
                "claimed_wins_contradicted": data["claims_contradicted"],
                "alerts_skipped_missing_quotes": data["alerts_skipped_missing_quote"],
                "alerts_skipped_chasing": data["alerts_skipped_chased"],
                "alerts_skipped_stale_timing": data["alerts_skipped_stale"],
                "estimated_win_rate": data["win_rate"],
                "average_paper_gain": data["average_gain"],
                "average_paper_loss": data["average_loss"],
                "main_caution_flags": _caution_flags(data),
                "main_promising_signals": _promising_signals(data),
                "conclusion": conclusion,
            },
            indent=2,
        )


def _caution_flags(data: dict) -> list[str]:
    flags = []
    if data["alerts_skipped_missing_quote"]:
        flags.append("quote data missing; cannot verify entry quality yet")
    if data["claims_not_enough_data"]:
        flags.append("source claims are unverified")
    if data["hype_potential_posts"]:
        flags.append("hype/potential language detected; do not count it as performance")
    if data["parser_misses"]:
        flags.append("some posts remain ambiguous parser misses")
    return flags


def _promising_signals(data: dict) -> list[str]:
    signals = []
    if data["clean_priced_entries"]:
        signals.append("clean priced option entries captured")
    if data["valid_missing_price_entries"]:
        signals.append("valid HERE contract alerts captured for review")
    if data["paper_copied_alerts"]:
        signals.append("local paper ledger is opening positions")
    return signals
