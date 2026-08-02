"""NDVI computation and Sentinel-2 DN -> reflectance conversion.

NDVI = (NIR - Red) / (NIR + Red), computed on surface reflectance.

Sentinel-2 L2A distributes reflectance as scaled integers. Since processing
baseline 04.00 (25 January 2022) the encoding includes an additive offset:
``reflectance = (DN - 1000) / 10000``. NDVI is a ratio, so the multiplicative
scale cancels — but the additive offset does NOT, and ignoring it materially
biases NDVI. :func:`resolve_band_scaling` picks the correct conversion, in
priority order:

1. ``raster:bands`` scale/offset from the STAC asset metadata, when present.
2. A heuristic on ``s2:processing_baseline`` (>= 04.00 → offset -0.1).
3. The pre-04.00 default (scale 1e-4, no offset).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

from earth_observation.types import BandScaling

FloatArray = npt.NDArray[np.floating]


def resolve_band_scaling(
    raster_bands: dict[str, Any] | None,
    processing_baseline: str | None,
) -> BandScaling:
    """Determine DN -> reflectance conversion for a scene's reflectance bands."""
    if raster_bands:
        scale = raster_bands.get("scale")
        offset = raster_bands.get("offset")
        if scale is not None or offset is not None:
            return BandScaling(
                scale=float(scale) if scale is not None else 1.0,
                offset=float(offset) if offset is not None else 0.0,
                source="raster_ext",
            )
    if processing_baseline is not None:
        try:
            baseline = float(processing_baseline)
        except ValueError:
            baseline = None
        if baseline is not None and baseline >= 4.0:
            return BandScaling(scale=1.0e-4, offset=-0.1, source="baseline_heuristic")
        if baseline is not None:
            return BandScaling(scale=1.0e-4, offset=0.0, source="baseline_heuristic")
    return BandScaling(scale=1.0e-4, offset=0.0, source="default")


def to_reflectance(dn: FloatArray, scaling: BandScaling) -> FloatArray:
    """Convert digital numbers to surface reflectance (float64 for precision)."""
    return dn.astype(np.float64) * scaling.scale + scaling.offset


def compute_ndvi(
    red: FloatArray,
    nir: FloatArray,
    valid_mask: npt.NDArray[np.bool_] | None = None,
) -> tuple[npt.NDArray[np.float32], int]:
    """Compute NDVI with explicit invalid-pixel handling.

    Negative reflectance inputs are clipped to zero before the ratio:
    negative surface reflectance is a retrieval artifact (common over water
    and deep shadow once the baseline-04.00 offset is removed), and without
    clipping a near-zero denominator produces physically meaningless NDVI
    values of arbitrary magnitude. With clipping the output is guaranteed to
    lie in [-1, 1].

    Returns ``(ndvi, zero_denominator_count)`` where ``ndvi`` is float32 with
    NaN at every pixel that is masked, non-finite in either input, or has a
    zero denominator (both bands zero after clipping). Zero-denominator
    pixels are counted separately because they indicate degenerate
    reflectance rather than clouds.
    """
    if red.shape != nir.shape:
        raise ValueError(f"Band shapes differ: red {red.shape} vs nir {nir.shape}")
    red64 = np.clip(red.astype(np.float64), 0.0, None)
    nir64 = np.clip(nir.astype(np.float64), 0.0, None)

    valid = np.isfinite(red64) & np.isfinite(nir64)
    if valid_mask is not None:
        if valid_mask.shape != red.shape:
            raise ValueError(f"Mask shape {valid_mask.shape} does not match band shape {red.shape}")
        valid &= valid_mask

    denominator = nir64 + red64
    zero_denominator = valid & (denominator == 0.0)
    zero_count = int(np.count_nonzero(zero_denominator))
    computable = valid & ~zero_denominator

    ndvi = np.full(red.shape, np.nan, dtype=np.float64)
    np.divide(nir64 - red64, denominator, out=ndvi, where=computable)
    return ndvi.astype(np.float32), zero_count
