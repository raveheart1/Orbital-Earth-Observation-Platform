"""Coverage accounting on the canonical grid.

Every AOI pixel of every observation lands in exactly one category, so a user
can always tell WHY a pixel did not contribute: the satellite never saw it,
the source carried nodata, cloud/shadow/cirrus masked it, snow masked it, a
sensor defect masked it, or the reflectance itself was unusable.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from earth_observation.types import CoverageStats, SCLClass

#: SCL classes grouped for reporting. A class only counts if the active mask
#: policy actually masks it.
_CLOUD_CLASSES = frozenset(
    {
        SCLClass.CLOUD_SHADOWS,
        SCLClass.CLOUD_MEDIUM_PROBABILITY,
        SCLClass.CLOUD_HIGH_PROBABILITY,
        SCLClass.THIN_CIRRUS,
    }
)
_SNOW_CLASSES = frozenset({SCLClass.SNOW_OR_ICE})


def compute_coverage(
    *,
    aoi_mask: npt.NDArray[np.bool_],
    covered: npt.NDArray[np.bool_],
    scl: npt.NDArray[np.floating],
    masked_classes: tuple[int, ...],
    spectral_finite: npt.NDArray[np.bool_],
    ndvi_finite: npt.NDArray[np.bool_],
    granule_count: int,
    contributing_item_ids: list[str],
    tile_ids: list[str],
) -> CoverageStats:
    """Classify every AOI pixel.

    Precedence (a pixel is counted once, in this order): uncovered → nodata →
    masked SCL class → invalid spectral value → valid. Precedence follows the
    physical chain: you cannot have cloud over ground the sensor never saw.
    """
    aoi_total = int(np.count_nonzero(aoi_mask))
    if aoi_total == 0:
        return CoverageStats(
            aoi_pixel_count=0,
            covered_pixel_count=0,
            uncovered_pixel_count=0,
            nodata_pixel_count=0,
            cloud_masked_pixel_count=0,
            snow_masked_pixel_count=0,
            other_masked_pixel_count=0,
            invalid_spectral_pixel_count=0,
            aoi_coverage_pct=0.0,
            valid_coverage_pct=0.0,
            masked_pct=0.0,
            missing_data_pct=0.0,
            granule_count=granule_count,
            contributing_item_ids=contributing_item_ids,
            tile_ids=tile_ids,
        )

    in_aoi = aoi_mask
    covered_aoi = in_aoi & covered
    uncovered = in_aoi & ~covered

    scl_classes = np.where(np.isfinite(scl), scl, -1).astype(np.int16)
    # Nodata: covered by a granule but the source itself had no value.
    # SCL class 0 (NO_DATA) and non-finite reflectance both mean "no usable
    # observation here" rather than "masked for quality".
    nodata = covered_aoi & (
        (scl_classes == int(SCLClass.NO_DATA)) | ~np.isfinite(scl) | ~spectral_finite
    )

    remaining = covered_aoi & ~nodata
    masked_set = set(masked_classes)
    cloud_hit = np.zeros_like(in_aoi)
    snow_hit = np.zeros_like(in_aoi)
    other_hit = np.zeros_like(in_aoi)
    for cls in masked_set:
        if cls == int(SCLClass.NO_DATA):
            continue  # already accounted as nodata
        hit = remaining & (scl_classes == np.int16(cls))
        if cls in _CLOUD_CLASSES:
            cloud_hit |= hit
        elif cls in _SNOW_CLASSES:
            snow_hit |= hit
        else:
            other_hit |= hit

    masked_any = cloud_hit | snow_hit | other_hit
    invalid_spectral = remaining & ~masked_any & ~ndvi_finite
    valid = remaining & ~masked_any & ~invalid_spectral

    def pct(count: int) -> float:
        return round(100.0 * count / aoi_total, 4)

    covered_count = int(np.count_nonzero(covered_aoi))
    uncovered_count = int(np.count_nonzero(uncovered))
    nodata_count = int(np.count_nonzero(nodata))
    cloud_count = int(np.count_nonzero(cloud_hit))
    snow_count = int(np.count_nonzero(snow_hit))
    other_count = int(np.count_nonzero(other_hit))
    invalid_count = int(np.count_nonzero(invalid_spectral))
    valid_count = int(np.count_nonzero(valid))

    return CoverageStats(
        aoi_pixel_count=aoi_total,
        covered_pixel_count=covered_count,
        uncovered_pixel_count=uncovered_count,
        nodata_pixel_count=nodata_count,
        cloud_masked_pixel_count=cloud_count,
        snow_masked_pixel_count=snow_count,
        other_masked_pixel_count=other_count,
        invalid_spectral_pixel_count=invalid_count,
        aoi_coverage_pct=pct(covered_count),
        valid_coverage_pct=pct(valid_count),
        masked_pct=pct(cloud_count + snow_count + other_count),
        missing_data_pct=pct(uncovered_count + nodata_count),
        granule_count=granule_count,
        contributing_item_ids=contributing_item_ids,
        tile_ids=tile_ids,
    )
