from __future__ import annotations


class DisabledBroker:
    provider = "disabled"
    mode = "none"

    def prepare_order_ticket(self, *_args, **_kwargs) -> dict:
        return {"status": "disabled", "reason": "broker execution is not enabled"}

    def execute(self, *_args, **_kwargs) -> None:
        raise RuntimeError("Broker execution is disabled for this build")


class TradierBrokerStub(DisabledBroker):
    provider = "tradier"

    def __init__(self, mode: str = "none", env: str = "sandbox", execution_enabled: bool = False, require_human_approval: bool = True):
        self.mode = mode
        self.env = env
        self.execution_enabled = execution_enabled
        self.require_human_approval = require_human_approval

    def prepare_order_ticket(self, *_args, **_kwargs) -> dict:
        return {
            "status": "disabled",
            "provider": self.provider,
            "mode": self.mode,
            "env": self.env,
            "execution_enabled": self.execution_enabled,
            "require_human_approval": self.require_human_approval,
            "reason": "Tradier is selected as the future broker path, but Sprint 1 does not submit orders.",
        }

    def execute(self, *_args, **_kwargs) -> None:
        raise RuntimeError("Tradier execution is disabled in Sprint 1")


def build_broker(settings):
    if settings.broker_provider == "tradier":
        return TradierBrokerStub(
            mode=settings.broker_mode,
            env=settings.tradier_env,
            execution_enabled=settings.broker_execution_enabled,
            require_human_approval=settings.require_human_approval,
        )
    return DisabledBroker()
