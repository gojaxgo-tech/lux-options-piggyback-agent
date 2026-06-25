from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HealthCheck:
    check_name: str
    status: str
    message: str


class HealthReporter:
    def __init__(self, database, settings):
        self.database = database
        self.settings = settings

    def run(self) -> list[HealthCheck]:
        state = self.database.get_control_state()
        checks = [
            self._database_check(),
            self._log_check(),
            HealthCheck("source_mode", "ok", f"source mode is {self.settings.source_mode}"),
            HealthCheck("notification_provider", "ok", f"notification provider is {self.settings.notification_provider}"),
            HealthCheck("llm", "ok", "LLM enabled" if self.settings.llm_enabled else "LLM disabled"),
            HealthCheck("openai_key", "ok" if self.settings.openai_api_key else ("error" if self.settings.llm_required else "warning"), "OPENAI_API_KEY configured" if self.settings.openai_api_key else "OPENAI_API_KEY missing; rules-only mode"),
            HealthCheck("market_data_provider", "ok", f"market data provider is {self.settings.market_data_provider}"),
            HealthCheck("broker_provider", "ok", f"broker provider is {self.settings.broker_provider}"),
            HealthCheck("broker_mode", "ok", f"broker mode is {self.settings.broker_mode}"),
            HealthCheck("broker_execution", "ok" if not self.settings.broker_execution_enabled else "error", f"broker_execution_enabled={self.settings.broker_execution_enabled}"),
            HealthCheck("human_approval", "ok" if self.settings.require_human_approval else "warning", f"require_human_approval={self.settings.require_human_approval}"),
            HealthCheck("tradier_env", "ok", f"tradier_env={self.settings.tradier_env}"),
            HealthCheck("kill_switch", "warning" if state.kill_switch else "ok", f"kill_switch={state.kill_switch}"),
            HealthCheck("paused", "warning" if state.paused else "ok", f"paused={state.paused}"),
            HealthCheck("autonomy_level", "ok", f"autonomy={state.autonomy_level.value}"),
            HealthCheck("last_source_check", "ok" if state.last_source_check_at else "warning", f"last_source_check_at={state.last_source_check_at}"),
            HealthCheck("last_successful_ingest", "ok" if state.last_successful_ingest_at else "warning", f"last_successful_ingest_at={state.last_successful_ingest_at}"),
        ]
        for check in checks:
            self.database.health(check.check_name, check.status, check.message)
        return checks

    def _database_check(self) -> HealthCheck:
        try:
            self.database.conn.execute("select 1").fetchone()
            writable = self.database.path.exists() and self.database.path.stat().st_size >= 0
            return HealthCheck("database", "ok" if writable else "warning", f"database reachable at {self.database.path}")
        except Exception as exc:
            return HealthCheck("database", "error", str(exc))

    def _log_check(self) -> HealthCheck:
        try:
            self.settings.log_file.parent.mkdir(parents=True, exist_ok=True)
            Path(self.settings.log_file).touch(exist_ok=True)
            return HealthCheck("disk_log", "ok", f"log writable at {self.settings.log_file}")
        except Exception as exc:
            return HealthCheck("disk_log", "error", str(exc))
