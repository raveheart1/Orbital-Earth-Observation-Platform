"""Spectral-index registry: one :class:`IndexDefinition` per supported operation.

Analyses are keyed by an operation name (``"ndvi"``, ``"nbr"``); the registry
maps that name to everything index-specific the pipeline needs: which band
roles must be discovered and mosaicked, how to compute the index from
reflectance, display ranges for previews, change-map scaling, and the
per-scene artifact file basenames.

The SCL role is deliberately NOT part of ``required_band_roles``: masking is
index-independent, so SCL is always required on top of the index's roles (see
:mod:`earth_observation.stac` and :mod:`earth_observation.processing`).

Adding an index (NDWI, EVI, ...) means adding a definition here plus its
colormap in :mod:`earth_observation.previews` — the pipeline is registry-driven.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from earth_observation.errors import UserInputError
from earth_observation.ndvi import FloatArray, compute_nbr, compute_ndvi
from earth_observation.previews import (
    legend_spec as ndvi_legend_spec,
)
from earth_observation.previews import (
    nbr_colormap_lut,
    nbr_legend_spec,
    ndvi_colormap_lut,
)

#: Signature shared by every index computation: the two band reflectances in
#: ``required_band_roles`` order, an optional valid mask, returning the float32
#: index array (NaN = invalid) and the zero-denominator pixel count.
IndexComputeFn = Callable[
    [FloatArray, FloatArray, npt.NDArray[np.bool_] | None],
    tuple[npt.NDArray[np.float32], int],
]


@dataclass(frozen=True)
class IndexDefinition:
    """Everything the pipeline needs to run one spectral index end to end."""

    operation: str
    """Operation name persisted on analyses and used as the registry key."""
    title: str
    """Human-facing name, e.g. for UI labels and legends."""
    formula: str
    """Plain-text formula recorded in provenance, e.g. ``(NIR - Red) / (NIR + Red)``."""
    required_band_roles: tuple[str, ...]
    """Spectral roles (AssetKeys attribute names) the index needs, in the order
    ``compute`` takes them. SCL is always required separately for masking."""
    compute: IndexComputeFn
    display_min: float
    display_max: float
    """Fixed preview display range; analytical outputs are never clamped."""
    change_display_range: float
    """Half-range of the change-map colormap (delta spans -range..+range)."""
    change_delta_threshold: float
    """Delta magnitude above which a pixel counts as changed in statistics."""
    interpretation: str
    """Short plain-language note on what the index does and does not show."""
    change_note: str
    """Caption for the change map; must state the delta's sign convention for
    this index and keep the "does not establish causes" caveat."""
    cog_basename: str
    preview_basename: str
    """Per-scene artifact file basenames (e.g. ``ndvi.tif``/``ndvi_preview.png``)."""
    colormap_lut: Callable[[], npt.NDArray[np.uint8]] = field(repr=False)
    """256-entry RGB lookup table used for the per-scene preview."""
    legend_builder: Callable[[float, float], dict[str, object]] = field(repr=False)
    """(display_min, display_max) -> preview-legend dict consumed by the web UI."""
    processing_warnings: tuple[str, ...] = ()
    """Warnings recorded on every scene processed with this index (e.g. the
    20 m -> 10 m SWIR resampling caveat for NBR)."""

    def legend_spec(self) -> dict[str, object]:
        """Preview legend for the web UI, matching this index's preview colormap."""
        return self.legend_builder(self.display_min, self.display_max)

    def __post_init__(self) -> None:
        # The shared compute machinery is a two-band normalized difference;
        # a future multi-band index (EVI) must relax this invariant together
        # with the compute call in processing.process_acquisition.
        if len(self.required_band_roles) != 2:
            raise ValueError(
                f"Index {self.operation!r} must require exactly 2 band roles, "
                f"got {self.required_band_roles}"
            )


NDVI = IndexDefinition(
    operation="ndvi",
    title="NDVI — vegetation health",
    formula="(NIR - Red) / (NIR + Red)",
    required_band_roles=("red", "nir"),
    compute=compute_ndvi,
    display_min=-0.2,
    display_max=0.9,
    change_display_range=0.4,
    change_delta_threshold=0.1,
    interpretation=(
        "NDVI = (NIR - Red) / (NIR + Red). Higher values indicate denser, "
        "healthier green vegetation; negative values indicate water, bare soil, "
        "or non-vegetated surfaces."
    ),
    change_note=(
        "Delta is the later minus the earlier NDVI for the specific "
        "acquisition dates shown; it does not by itself establish "
        "causes, and individual 10 m pixels are spectral mixtures "
        "that shift slightly between dates. See the limitations "
        "documentation."
    ),
    cog_basename="ndvi.tif",
    preview_basename="ndvi_preview.png",
    colormap_lut=ndvi_colormap_lut,
    legend_builder=ndvi_legend_spec,
)

NBR = IndexDefinition(
    operation="nbr",
    title="NBR — burn severity",
    formula="(NIR - SWIR2) / (NIR + SWIR2)",
    required_band_roles=("nir", "swir"),
    compute=compute_nbr,
    display_min=-1.0,
    display_max=1.0,
    change_display_range=0.6,
    change_delta_threshold=0.1,
    interpretation=(
        "NBR = (NIR - SWIR2) / (NIR + SWIR2). Healthy vegetation is strongly "
        "NIR-reflective and SWIR-absorptive (high NBR); recently burned or bare "
        "surfaces drop low or negative, so a negative change between dates is "
        "consistent with burning. NBR is a spectral signal only — it does not "
        "by itself confirm fire."
    ),
    change_note=(
        "Delta is the later minus the earlier NBR for the specific "
        "acquisition dates shown. NBR drops over burned or severely damaged "
        "vegetation, so a negative delta indicates burn severity increase "
        "(new burn) and a positive delta indicates recovery or regrowth. "
        "It does not by itself establish causes, and individual 10 m pixels "
        "are spectral mixtures that shift slightly between dates; the SWIR "
        "band is natively 20 m and resampled onto the 10 m grid. See the "
        "limitations documentation."
    ),
    cog_basename="nbr.tif",
    preview_basename="nbr_preview.png",
    colormap_lut=nbr_colormap_lut,
    legend_builder=nbr_legend_spec,
    processing_warnings=(
        "SWIR band B12 has 20 m native resolution and is resampled onto the "
        "10 m grid with bilinear interpolation, so NBR values near sharp "
        "boundaries are smoothed",
    ),
)

#: All supported indices, keyed by operation name.
INDICES: dict[str, IndexDefinition] = {d.operation: d for d in (NDVI, NBR)}


def get_index(operation: str) -> IndexDefinition:
    """Look up the index definition for an operation name.

    Raises :class:`UserInputError` for unknown operations — an unsupported
    operation is a deterministic request error, never worth retrying.
    """
    try:
        return INDICES[operation]
    except KeyError:
        raise UserInputError(
            f"Unknown operation {operation!r}; available operations: {sorted(INDICES)}"
        ) from None
