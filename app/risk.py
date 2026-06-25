from __future__ import annotations


class DisabledBrokerRisk:
    def can_execute_live_trade(self) -> bool:
        return False


RiskEngine = DisabledBrokerRisk

