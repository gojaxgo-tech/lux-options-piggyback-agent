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
        return self.performance()
