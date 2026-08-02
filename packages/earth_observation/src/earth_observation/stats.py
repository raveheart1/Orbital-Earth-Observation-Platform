"""NDVI statistics over valid pixels only."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from earth_observation.types import SceneStats


def compute_scene_stats(
    ndvi: npt.NDArray[np.floating],
    aoi_mask: npt.NDArray[np.bool_],
    zero_denominator_count: int,
) -> SceneStats:
    """Compute per-scene statistics.

    ``aoi_mask`` is True for pixels inside the AOI footprint; statistics use
    only pixels that are inside the AOI AND have a finite NDVI value. Masked
    (cloud/nodata/zero-denominator) pixels never contribute to any statistic.
    """
    if ndvi.shape != aoi_mask.shape:
        raise ValueError(f"NDVI shape {ndvi.shape} does not match AOI mask shape {aoi_mask.shape}")
    aoi_pixels = int(np.count_nonzero(aoi_mask))
    valid = aoi_mask & np.isfinite(ndvi)
    valid_count = int(np.count_nonzero(valid))
    masked_count = aoi_pixels - valid_count
    pct = (100.0 * valid_count / aoi_pixels) if aoi_pixels > 0 else 0.0

    if valid_count == 0:
        return SceneStats(
            valid_pixel_count=0,
            masked_pixel_count=masked_count,
            aoi_pixel_count=aoi_pixels,
            valid_pixel_pct=0.0,
            zero_denominator_pixel_count=zero_denominator_count,
            ndvi_min=None,
            ndvi_max=None,
            ndvi_mean=None,
            ndvi_median=None,
            ndvi_std=None,
            ndvi_p10=None,
            ndvi_p25=None,
            ndvi_p75=None,
            ndvi_p90=None,
        )

    values = ndvi[valid].astype(np.float64)
    p10, p25, p75, p90 = np.percentile(values, [10, 25, 75, 90])
    return SceneStats(
        valid_pixel_count=valid_count,
        masked_pixel_count=masked_count,
        aoi_pixel_count=aoi_pixels,
        valid_pixel_pct=round(pct, 4),
        zero_denominator_pixel_count=zero_denominator_count,
        ndvi_min=float(values.min()),
        ndvi_max=float(values.max()),
        ndvi_mean=float(values.mean()),
        ndvi_median=float(np.median(values)),
        ndvi_std=float(values.std(ddof=0)),
        ndvi_p10=float(p10),
        ndvi_p25=float(p25),
        ndvi_p75=float(p75),
        ndvi_p90=float(p90),
    )
