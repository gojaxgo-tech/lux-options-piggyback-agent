from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.models import AutonomyLevel


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _sqlite_path(database_url: str) -> Path:
    if database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///"))
    return Path(database_url)


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    timezone: str
    database_url: str
    db_path: Path
    log_level: str
    log_file: Path
    source_platform: str
    source_account: str
    source_mode: str
    x_bearer_token: str
    notification_provider: str
    telegram_bot_token: str
    telegram_chat_id: str
    llm_enabled: bool
    llm_required: bool
    llm_provider: str
    openai_api_key: str
    llm_model_fast: str
    llm_model_review: str
    llm_model_deep: str
    llm_use_deep: bool
    llm_max_calls_per_day: int
    llm_calls_only_on_low_confidence: bool
    market_data_provider: str
    broker_provider: str
    broker_mode: str
    autonomy_level: AutonomyLevel
    broker_execution_enabled: bool
    require_human_approval: bool
    tradier_env: str
    tradier_access_token: str
    tradier_account_id: str
    public_x_engagement: bool
    kill_switch: bool
    poll_interval_seconds: int
    stale_source_warning_minutes: int
    max_entry_slippage_pct: float
    max_spread_pct: float
    source_posts_file: str | None


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    _load_dotenv()
    database_url = os.getenv("DATABASE_URL", "sqlite:///data/sniper_alert.sqlite")
    return Settings(
        app_name=os.getenv("APP_NAME", "Sniper Alert"),
        app_env=os.getenv("APP_ENV", "production"),
        timezone=os.getenv("TIMEZONE", "America/Los_Angeles"),
        database_url=database_url,
        db_path=_sqlite_path(database_url),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=Path(os.getenv("LOG_FILE", "logs/sniper_alert.log")),
        source_platform=os.getenv("SOURCE_PLATFORM", "x"),
        source_account=os.getenv("SOURCE_ACCOUNT", "StockOptions888").lstrip("@"),
        source_mode=os.getenv("SOURCE_MODE", "manual"),
        x_bearer_token=os.getenv("X_BEARER_TOKEN", ""),
        notification_provider=os.getenv("NOTIFICATION_PROVIDER", "console"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        llm_enabled=env_bool("LLM_ENABLED", True),
        llm_required=env_bool("LLM_REQUIRED", False),
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        llm_model_fast=os.getenv("LLM_MODEL_FAST", "gpt-5.4-nano"),
        llm_model_review=os.getenv("LLM_MODEL_REVIEW", "gpt-5.4-mini"),
        llm_model_deep=os.getenv("LLM_MODEL_DEEP", "gpt-5.5"),
        llm_use_deep=env_bool("LLM_USE_DEEP", False),
        llm_max_calls_per_day=int(os.getenv("LLM_MAX_CALLS_PER_DAY", "200")),
        llm_calls_only_on_low_confidence=env_bool("LLM_CALLS_ONLY_ON_LOW_CONFIDENCE", True),
        market_data_provider=os.getenv("MARKET_DATA_PROVIDER", "none"),
        broker_provider=os.getenv("BROKER_PROVIDER", "tradier"),
        broker_mode=os.getenv("BROKER_MODE", "none"),
        autonomy_level=AutonomyLevel(os.getenv("AUTONOMY_LEVEL", "monitor_only")),
        broker_execution_enabled=env_bool("BROKER_EXECUTION_ENABLED", False),
        require_human_approval=env_bool("REQUIRE_HUMAN_APPROVAL", True),
        tradier_env=os.getenv("TRADIER_ENV", "sandbox"),
        tradier_access_token=os.getenv("TRADIER_ACCESS_TOKEN", ""),
        tradier_account_id=os.getenv("TRADIER_ACCOUNT_ID", ""),
        public_x_engagement=env_bool("PUBLIC_X_ENGAGEMENT", False),
        kill_switch=env_bool("KILL_SWITCH", False),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
        stale_source_warning_minutes=int(os.getenv("STALE_SOURCE_WARNING_MINUTES", "30")),
        max_entry_slippage_pct=float(os.getenv("MAX_ENTRY_SLIPPAGE_PCT", "20")),
        max_spread_pct=float(os.getenv("MAX_SPREAD_PCT", "25")),
        source_posts_file=os.getenv("SOURCE_POSTS_FILE") or os.getenv("LUX_SOURCE_POSTS_FILE") or None,
    )
