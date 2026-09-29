"""Validated analysis options persisted on ``analyses.options``.

The request contract (``oeop_api.schemas``) validates what a client may ask
for; this model is what the API stores and the worker reads. It is a snapshot
like ``processing_config``: configuration, not queryable measurement data, so
it lives in one JSON column rather than a spread of nullable columns. The
one option that IS queried — which workflow an analysis runs — has its own
``analyses.workflow`` column.

Analyses created before options existed have ``options = NULL``; they parse
to the defaults below, which reproduce their original behaviour exactly (no
land-cover stratification, no temporal context).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Workflow = Literal["timeseries", "wildfire_dnbr"]
WORKFLOWS: tuple[str, ...] = ("timeseries", "wildfire_dnbr")
DEFAULT_WORKFLOW = "timeseries"


class TemporalOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    enabled: bool = False
    baseline_years: int = Field(default=5, ge=1)


class WildfireOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    pre_fire_start: date
    pre_fire_end: date
    post_fire_start: date
    post_fire_end: date
    severity_classification: bool = True
    severity_scheme: str = "key-benson-2006"
    custom_thresholds: list[float] | None = None
    event: dict[str, Any] | None = Field(
        default=None,
        description="Snapshot of the region's documented fire event, when the "
        "analysis ran over a curated wildfire region (context only)",
    )


class AnalysisOptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    land_cover: bool = False
    land_cover_dataset: str | None = Field(
        default=None, description="Explicit dataset id; None = choose by documented rule"
    )
    temporal: TemporalOptions = TemporalOptions()
    wildfire: WildfireOptions | None = None


def parse_options(raw: dict[str, Any] | None) -> AnalysisOptions:
    """Options of a stored analysis; ``None`` (legacy rows) → defaults."""
    return AnalysisOptions.model_validate(raw or {})
