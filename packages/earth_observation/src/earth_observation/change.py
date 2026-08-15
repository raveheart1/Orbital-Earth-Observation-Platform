"""Per-pixel NDVI change between two observations of one analysis.

Both inputs must lie on the canonical analysis grid, which guarantees they
describe the identical ground. ``delta = later - earlier`` (positive =
greening). A pixel has a defined change only when it is valid in BOTH
observations — a pixel that is cloud-masked, nodata, or uncovered on either
date carries NaN, following the package-wide NaN-is-invalid convention.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from earth_observation.types import ChangeStats


def compute_change(
    earlier: npt.NDArray[np.float32],
    later: npt.NDArray[np.float32],
    aoi_mask: npt.NDArray[np.bool_],
    *,
    delta_threshold: float,
) -> tuple[npt.NDArray[np.float32], ChangeStats]:
    """Compute the per-pixel NDVI change map and its statistics.

    ``delta_threshold`` is the |delta| a pixel must exceed to count toward
    ``pct_increased`` / ``pct_decreased``; smaller changes still contribute to
    every other statistic. All statistics are computed over pixels inside the
    AOI that are finite in both inputs.
    """
    if earlier.shape != later.shape:
        raise ValueError(
            f"Observation shapes differ: earlier {earlier.shape} vs later {later.shape}"
        )
    if aoi_mask.shape != earlier.shape:
        raise ValueError(
            f"AOI mask shape {aoi_mask.shape} does not match observation shape {earlier.shape}"
        )
    if delta_threshold <= 0:
        raise ValueError("delta_threshold must be positive")

    valid_both = aoi_mask & np.isfinite(earlier) & np.isfinite(later)
    delta = np.full(earlier.shape, np.nan, dtype=np.float32)
    np.subtract(later, earlier, out=delta, where=valid_both)

    aoi_pixels = int(np.count_nonzero(aoi_mask))
    valid_count = int(np.count_nonzero(valid_both))
    valid_pct = (100.0 * valid_count / aoi_pixels) if aoi_pixels > 0 else 0.0

    if valid_count == 0:
        return delta, ChangeStats(
            aoi_pixel_count=aoi_pixels,
            valid_both_pixel_count=0,
            valid_both_pct=0.0,
            delta_mean=None,
            delta_median=None,
            delta_std=None,
            delta_p10=None,
            delta_p90=None,
            pct_increased=None,
            pct_decreased=None,
        )

    values = delta[valid_both].astype(np.float64)
    p10, p90 = np.percentile(values, [10, 90])
    increased = int(np.count_nonzero(values > delta_threshold))
    decreased = int(np.count_nonzero(values < -delta_threshold))
    return delta, ChangeStats(
        aoi_pixel_count=aoi_pixels,
        valid_both_pixel_count=valid_count,
        valid_both_pct=round(valid_pct, 4),
        delta_mean=float(values.mean()),
        delta_median=float(np.median(values)),
        delta_std=float(values.std(ddof=0)),
        delta_p10=float(p10),
        delta_p90=float(p90),
        pct_increased=round(100.0 * increased / valid_count, 4),
        pct_decreased=round(100.0 * decreased / valid_count, 4),
    )
