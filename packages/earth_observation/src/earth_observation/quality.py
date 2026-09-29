"""Machine-readable result quality and epistemic level.

Two small vocabularies are shared by every derived result the platform
produces (land-cover class statistics, temporal baselines and anomalies,
trends, phenology, dNBR, severity classes):

* :class:`QualityState` — whether a result is fit for interpretation, and if
  not, WHY. Structured states replace prose warnings so the API and UI can
  react to them, and so missing or inadequate data is never silently turned
  into a zero or a number with fabricated precision. A result that could not
  be computed carries a state and ``null`` values — never a default.

* :class:`ResultKind` — the epistemic level of a result. OEOP keeps four
  levels distinct, all the way from the data model to the UI:

  - ``observation`` — what the sensor recorded: acquisitions, dates, source
    scenes, cloud cover.
  - ``measurement`` — a value derived deterministically from observations:
    NDVI/NBR statistics, class areas, dNBR.
  - ``statistical_inference`` — a statement that depends on a statistical
    model or estimator: seasonal baselines, anomalies, trends, significance.
  - ``interpretation`` — a mapping of measurements onto a human category
    under a documented convention: burn-severity classes, "unusually low".

  None of the four is a causal claim; the platform makes none.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QualityState(str, Enum):
    """Primary quality classification of a derived result.

    ``state`` names the most important applicable condition. It does not by
    itself say whether values exist: a ``seasonal_mismatch`` dNBR is still
    computed (and flagged), while an ``insufficient_history`` anomaly has no
    values. Consumers check the result's own nullable fields.
    """

    VALID = "valid"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    INSUFFICIENT_HISTORY = "insufficient_history"
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    SEASONAL_MISMATCH = "seasonal_mismatch"
    CLOUD_CONTAMINATED = "cloud_contaminated"
    UNSUPPORTED = "unsupported"


class ResultKind(str, Enum):
    """Epistemic level of a result (see module docstring)."""

    OBSERVATION = "observation"
    MEASUREMENT = "measurement"
    STATISTICAL_INFERENCE = "statistical_inference"
    INTERPRETATION = "interpretation"


class QualityInfo(BaseModel):
    """Structured quality metadata attached to a derived result.

    ``reasons`` are stable machine codes (e.g. ``"valid_fraction_below_threshold"``);
    ``details`` carries the numbers behind them (thresholds and observed
    values) so a reader can see how close to a threshold a result was;
    ``flags`` are secondary, non-blocking conditions (e.g.
    ``"reference_year_mismatch"``) that apply even when ``state`` is valid.
    """

    model_config = ConfigDict(frozen=True)

    state: QualityState = QualityState.VALID
    reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.state is QualityState.VALID


def valid(message: str = "", *, flags: list[str] | None = None, **details: Any) -> QualityInfo:
    """A valid result, optionally carrying non-blocking flags."""
    return QualityInfo(
        state=QualityState.VALID,
        flags=list(flags or []),
        message=message,
        details=details,
    )


def degraded(
    state: QualityState,
    reason: str,
    message: str,
    *,
    flags: list[str] | None = None,
    **details: Any,
) -> QualityInfo:
    """A result whose ``state`` is not valid, with one primary reason code."""
    if state is QualityState.VALID:
        raise ValueError("degraded() requires a non-valid state; use valid()")
    return QualityInfo(
        state=state,
        reasons=[reason],
        flags=list(flags or []),
        message=message,
        details=details,
    )
