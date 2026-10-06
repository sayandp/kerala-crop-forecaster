"""Central configuration. ALL environment variables are read here and nowhere else."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

IngestSource = Literal["agmarknet", "datagov"]
DEFAULT_SOURCES: tuple[IngestSource, ...] = ("agmarknet", "datagov")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["local", "ci", "prod"] = "local"

    # --- Database ---
    database_url: str = "postgresql+psycopg://cropcast:cropcast@localhost:5432/cropcast"
    # Throwaway database for DB tests (they TRUNCATE tables). Tests skip when unset/unreachable.
    test_database_url: str | None = None

    # Free-tier budget (Neon 0.5 GB): keep the DB under budget; ping admin above warn.
    db_budget_mb: float = 400.0
    db_warn_mb: float = 350.0

    # --- data.gov.in "Current Daily Price of Various Commodities from Various Markets (Mandi)"
    # Returns today's prices only; history is accumulated by the daily pull.
    datagov_api_key: SecretStr | None = None
    datagov_resource_id: str = "9ef84268-d588-465a-a308-a864a43d0070"
    datagov_base_url: str = "https://api.data.gov.in/resource"
    datagov_page_size: int = 1000

    # --- Agmarknet 2.0 public report API (backfill + daily fallback) ---
    agmarknet_api_base: str = "https://api.agmarknet.gov.in/v1"
    agmarknet_state_id: int = 17  # "Keralam" in Agmarknet 2.0 masters
    # Agmarknet commodity ids for the target crops (from /daily-price-arrival/filters).
    agmarknet_commodity_ids: dict[str, int] = Field(
        default_factory=lambda: {
            "Banana": 19,
            "Banana - Green": 76,
            "Coconut": 116,
            "Rubber": 95,
            "Black pepper": 34,
            "Pepper garbled": 93,
            "Pepper ungarbled": 94,
            "Tapioca": 85,
        }
    )

    # Daily ingest sources, tried in order. Agmarknet 2.0 is primary: same naming as the
    # backfill (no split series), serves any date (late-report lookback), no API key.
    # data.gov.in is the fallback (it only ever serves "today").
    ingest_sources: list[IngestSource] = Field(default_factory=lambda: list(DEFAULT_SOURCES))
    # Re-pull this many days before the run date to catch late market reports.
    ingest_lookback_days: int = 3

    # --- Archive: prices_raw keeps this many days in the DB (older -> GitHub Release) ---
    archive_after_days: int = 90

    # --- Clean layer (prices_clean) ---
    # Agmarknet 2.0 cut-over: old variety labels end 2025-11-06, new ones start here.
    portal_switch_date: date = date(2025, 11, 7)
    clean_window_days: int = 30  # incremental rebuild window; --full rebuilds everything
    alias_guard_tolerance: float = 0.10  # |median(before)/median(after) - 1| must be <= this
    alias_guard_window_days: int = 30
    alias_guard_min_obs: int = 5  # per side, else the merge is rejected as "insufficient data"

    # --- Open-Meteo ---
    openmeteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    openmeteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    openmeteo_archive_interval_s: float = 30.0

    # --- Domain ---
    state: str = "Kerala"
    target_commodities: list[str] = Field(
        default_factory=lambda: ["banana", "coconut", "rubber", "pepper", "tapioca"]
    )

    # --- HTTP politeness ---
    http_timeout_s: float = 60.0
    request_delay_s: float = 2.0
    user_agent: str = "cropcast/0.1 (+https://github.com/; Kerala crop price research)"

    # --- Validation ---
    max_reject_fraction: float = 0.20

    # --- Paths ---
    data_dir: Path = PROJECT_ROOT / "data"
    reports_dir: Path = PROJECT_ROOT / "reports"
    logs_dir: Path = PROJECT_ROOT / "logs"

    # --- MLflow (later phases) ---
    mlflow_tracking_uri: str | None = None
    mlflow_tracking_username: str | None = None
    mlflow_tracking_password: SecretStr | None = None

    # --- Telegram ---
    telegram_bot_token: SecretStr | None = None
    telegram_admin_chat_id: str | None = None
    telegram_channel_id: str | None = None  # public channel for the daily Stage-1 post

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
