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
    blob_download_base_url: str | None = Field(
        default=None,
        description="Client-reachable base URL substituted for the storage endpoint "
        "in generated download URLs. Needed when the endpoint the API talks to is "
        "not resolvable by browsers — e.g. docker compose, where the API reaches "
        "Azurite at http://azurite:10000 but the host only publishes it as "
        "http://localhost:10000/devstoreaccount1.",
    )
    artifacts_container: str = "artifacts"
    analysis_queue_name: str = "analysis-jobs"
    poison_queue_name: str = "analysis-jobs-poison"

    # --- Processing constraints & cost controls -----------------------------
    max_aoi_area_km2: float = Field(default=600.0, description="Maximum AOI area")
    min_aoi_area_km2: float = Field(default=0.5, description="Reject degenerate AOIs")
    max_date_span_days: int = Field(
        default=3660,
        description="Maximum requested date span (~10 years). Long spans are "
        "affordable because cost is bounded by scene_limit and AOI area, not by "
        "the span: the extra work is metadata-only STAC queries. Use the "
        "seasonal selection strategy for multi-year comparisons.",
    )
    min_start_date: date = Field(
        default=date(2015, 7, 1),
        description="Earliest queryable date. Sentinel-2A reached orbit in mid-2015; "
        "coverage before 2017 is sparse (one satellite, ~10-day revisit) and "
        "correspondingly cloudier in practice.",
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
    demo_max_date_span_days: int = Field(
        default=3660,
        description="Demo mode does not tighten the span: a multi-year analysis "
        "costs the same as a short one because scene_limit bounds the processing.",
    )
    max_seasonal_tolerance_days: int = Field(
        default=45,
        description="Ceiling on how far a seasonal-strategy observation may fall "
        "from its target day-of-year",
    )
    allow_custom_areas: bool = Field(
        default=True,
        description="Allow visitor-drawn areas of interest in addition to the "
        "predefined regions, including while DEMO_MODE is on. Custom areas are "
        "capped separately by max_custom_aoi_area_km2.",
    )
    max_custom_aoi_area_km2: float = Field(
        default=250.0,
        description="Maximum area for a visitor-DRAWN AOI, in km². Set from measured "
        "cost: outputs run ~0.06 MB per scene per km², so the 200 MB "
        "per_analysis_storage_limit_mb is reached near 417 km² at 8 scenes and "
        "278 km² at 12. 250 km² keeps a margin below both, matches the curated "
        "regions' ceiling so users see one number, and processes in about three "
        "minutes — far inside max_job_runtime_seconds.",
    )
    max_custom_aoi_vertices: int = Field(
        default=256,
        description="Vertex ceiling for a drawn polygon's exterior ring, excluding "
        "the closing vertex. Generous for anything hand-drawn on a map while "
        "bounding the cost of every downstream geometry operation on an "
        "arbitrary public submission.",
    )
    rate_limit_submissions_per_hour: int = Field(
        default=10, description="Best-effort per-client submission throttle (per replica)"
    )

    # --- Scientific expansion: land cover, temporal context, wildfire -------
    land_cover_enabled: bool = Field(
        default=True,
        description="Kill switch for land-cover stratification (ESA WorldCover). When "
        "false, analyses are stored with land cover disabled regardless of the request",
    )
    land_cover_cache_enabled: bool = Field(
        default=True,
        description="Reuse land-cover rasters already aligned to an identical grid "
        "(blob prefix cache/land-cover/); deterministic keys, safe to delete",
    )
    temporal_context_enabled: bool = Field(
        default=True,
        description="Allow temporal context (seasonal baseline, anomalies, trend). "
        "Each request measures up to TemporalConfig.max_baseline_acquisitions extra "
        "historical acquisitions (statistics only, no artifacts)",
    )
    default_baseline_years: int = Field(
        default=5, description="Default reference-period length in calendar years"
    )
    max_baseline_years: int = Field(
        default=8, description="Ceiling on the requested reference-period length"
    )
    historical_measurement_concurrency: int = Field(
        default=4,
        description="Threads measuring historical acquisitions in parallel (network "
        "bound COG range reads); results are ordered deterministically afterwards",
    )
    wildfire_enabled: bool = Field(
        default=True, description="Allow the wildfire_dnbr (pre/post-fire dNBR) workflow"
    )
    max_fire_window_days: int = Field(
        default=366, description="Maximum length of each pre-fire / post-fire window"
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

    # --- FIRMS active-fire overlay (optional) -------------------------------
    firms_map_key: str | None = Field(
        default=None,
        description="NASA FIRMS Area API key (secret). None disables the "
        "active-fire overlay entirely — it is an optional deployment feature "
        "and its absence or failure never fails an analysis",
    )
    firms_source: str = Field(
        default="VIIRS_SNPP_SP",
        description="FIRMS product for the overlay. Standard processing (SP) "
        "covers the full archive back to 2012; NRT products only cover recent "
        "days, and analysis spans may reach years back",
    )
    firms_max_windows: int = Field(
        default=75,
        description="Cap on FIRMS API calls per analysis (cost control; the "
        "key allows 5000 transactions per 10 minutes and multi-day requests "
        "count as several). At 5 days per call this covers ~1 year of date "
        "span; longer spans are truncated and the truncation is recorded in "
        "the artifact metadata",
    )
    firms_timeout_seconds: float = Field(
        default=30.0, description="Per-request timeout for FIRMS API calls"
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

    def effective_max_custom_aoi_area_km2(self) -> float:
        """Ceiling for a drawn AOI.

        Never exceeds the global AOI ceiling, so tightening
        ``max_aoi_area_km2`` also tightens custom areas.
        """
        return min(self.max_custom_aoi_area_km2, self.max_aoi_area_km2)

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
