"""Application settings.

Every processing constraint and cost control is configuration, not code.
Values load from the environment with the ``OEOP_`` prefix (see
``.env.example``). Defaults are conservative and suitable for a public
portfolio demonstration.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OEOP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = "local"
    log_level: str = "INFO"

    # --- Database -----------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://oeop:oeop_local_dev@localhost:5432/oeop",
        description="SQLAlchemy async URL; production value is injected from Key Vault",
    )

    # --- Storage & queue ----------------------------------------------------
    storage_connection_string: str | None = Field(
        default=None,
        description="Connection string for Azurite or key-based access (local dev only)",
    )
    blob_account_url: str | None = Field(
        default=None,
        description="https://<account>.blob.core.windows.net — used with managed identity",
    )
    queue_account_url: str | None = Field(
        default=None,
        description="https://<account>.queue.core.windows.net — used with managed identity",
    )
    artifacts_container: str = "artifacts"
    analysis_queue_name: str = "analysis-jobs"
    poison_queue_name: str = "analysis-jobs-poison"

    # --- Processing constraints & cost controls -----------------------------
    max_aoi_area_km2: float = Field(default=600.0, description="Maximum AOI area")
    min_aoi_area_km2: float = Field(default=0.5, description="Reject degenerate AOIs")
    max_date_span_days: int = Field(default=730, description="Maximum requested date span")
    min_start_date: date = Field(
        default=date(2016, 1, 1),
        description="Earliest queryable date (Sentinel-2 archive availability)",
    )
    max_scene_limit: int = Field(default=12, description="Server-side scene-count ceiling")
    default_scene_limit: int = 6
    max_cloud_cover_pct: float = Field(default=80.0, description="Ceiling for the request knob")
    default_cloud_cover_pct: float = 20.0
    max_job_runtime_seconds: int = Field(default=1500, description="Worker hard deadline")
    max_dequeue_count: int = Field(
        default=3, description="Deliveries before a message moves to the poison queue"
    )
    queue_visibility_timeout_seconds: int = 300
    queue_poll_interval_seconds: float = 5.0
    preview_max_dim: int = 1024
    output_retention_days: int = Field(
        default=30, description="Blob lifecycle policy target; documented, enforced in Azure"
    )
    per_analysis_storage_limit_mb: int = Field(
        default=200, description="Hard cap on bytes uploaded per analysis"
    )

    # --- Demo / abuse controls ---------------------------------------------
    demo_mode: bool = Field(
        default=False,
        description="When true, new submissions are restricted to predefined regions "
        "and tighter limits; precomputed results remain browsable",
    )
    submissions_enabled: bool = Field(
        default=True,
        description="Kill switch: disable new analyses entirely while keeping reads",
    )
    demo_max_aoi_area_km2: float = 250.0
    demo_max_scene_limit: int = 8
    demo_max_date_span_days: int = 400
    rate_limit_submissions_per_hour: int = Field(
        default=10, description="Best-effort per-client submission throttle (per replica)"
    )

    # --- API ----------------------------------------------------------------
    cors_allowed_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated exact origins allowed for browser calls",
    )
    max_request_body_bytes: int = 64 * 1024
    download_url_ttl_seconds: int = Field(
        default=900, description="Lifetime of generated artifact download URLs"
    )

    # --- Build / provenance metadata ---------------------------------------
    git_commit_sha: str | None = Field(
        default=None, validation_alias=AliasChoices("OEOP_GIT_COMMIT_SHA", "GIT_COMMIT_SHA")
    )
    container_image: str | None = Field(
        default=None, validation_alias=AliasChoices("OEOP_CONTAINER_IMAGE", "CONTAINER_IMAGE")
    )

    # --- Telemetry ----------------------------------------------------------
    applicationinsights_connection_string: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "OEOP_APPLICATIONINSIGHTS_CONNECTION_STRING",
        ),
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    def effective_max_aoi_area_km2(self) -> float:
        return (
            min(self.max_aoi_area_km2, self.demo_max_aoi_area_km2)
            if self.demo_mode
            else self.max_aoi_area_km2
        )

    def effective_max_scene_limit(self) -> int:
        return (
            min(self.max_scene_limit, self.demo_max_scene_limit)
            if self.demo_mode
            else self.max_scene_limit
        )

    def effective_max_date_span_days(self) -> int:
        return (
            min(self.max_date_span_days, self.demo_max_date_span_days)
            if self.demo_mode
            else self.max_date_span_days
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
