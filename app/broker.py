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

    def __init__(
        self,
        mode: str = "none",
        env: str = "sandbox",
        execution_enabled: bool = False,
        require_human_approval: bool = True,
        enable_sandbox_orders: bool = False,
    ):
        self.mode = mode
        self.env = env
        self.execution_enabled = execution_enabled
        self.require_human_approval = require_human_approval
        self.enable_sandbox_orders = enable_sandbox_orders

    def prepare_order_ticket(self, *_args, **_kwargs) -> dict:
        return {
            "status": "disabled",
            "provider": self.provider,
            "mode": self.mode,
            "env": self.env,
            "execution_enabled": self.execution_enabled,
            "require_human_approval": self.require_human_approval,
            "reason": "Tradier is selected as the future broker path, but Sniper Alert does not submit live orders.",
        }

    def execute(self, *_args, **_kwargs) -> None:
        raise RuntimeError("Tradier live execution is disabled for Sniper Alert")

    def submit_sandbox_paper_order(self, *_args, **_kwargs) -> dict:
        if self.env != "sandbox":
            raise RuntimeError("Tradier sandbox paper orders refuse to run outside sandbox")
        if not self.enable_sandbox_orders:
            return {"status": "disabled", "reason": "ENABLE_TRADIER_SANDBOX_ORDERS=false; no sandbox order submitted"}
        if not self.execution_enabled:
            return {"status": "disabled", "reason": "BROKER_EXECUTION_ENABLED=false; no sandbox order submitted"}
        return {"status": "disabled", "reason": "Sandbox order submission is stubbed for review-only Sprint 2B"}


def build_broker(settings):
    if settings.broker_provider == "tradier":
        return TradierBrokerStub(
            mode=settings.broker_mode,
            env=settings.tradier_env,
            execution_enabled=settings.broker_execution_enabled,
            require_human_approval=settings.require_human_approval,
            enable_sandbox_orders=settings.enable_tradier_sandbox_orders,
        )
    return DisabledBroker()
