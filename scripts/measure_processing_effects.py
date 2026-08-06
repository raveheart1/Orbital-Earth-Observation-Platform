"""Measure what each correctness step is worth, in NDVI units, on live imagery.

The case study claims that handling the Sentinel-2 baseline-04.00 additive
offset "materially biases the index" and that cloud masking matters. Those are
checkable claims, so this script checks them: it processes a real acquisition
normally, then re-processes it with one step disabled at a time and reports the
difference.

    uv run python scripts/measure_processing_effects.py

Requires network (Planetary Computer). Nothing is written; results go to stdout
so the figures quoted in docs/ can be regenerated and audited.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import box, mapping

from earth_observation.acquisition import Acquisition, group_acquisitions
from earth_observation.grid import CanonicalGrid
from earth_observation.masking import scl_valid_mask
from earth_observation.mosaic import mosaic_band
from earth_observation.ndvi import compute_ndvi, resolve_band_scaling, to_reflectance
from earth_observation.stac import search_scenes, sign_href
from earth_observation.types import BandScaling, ProcessingConfig

#: The demonstration region, so these numbers line up with the published analysis.
BBOX = (-83.30, 42.55, -83.15, 42.65)
START, END = "2024-04-01", "2024-10-31"

#: Deliberately permissive: the point is to include scenes the platform would
#: normally reject, so the masking step has something to do.
MAX_CLOUD_PCT = 80.0


def _mean(ndvi: np.ndarray, mask: np.ndarray, aoi: np.ndarray) -> tuple[float, int]:
    selected = mask & aoi & np.isfinite(ndvi)
    return float(np.nanmean(ndvi[selected])), int(selected.sum())


def measure(acquisition: Acquisition, grid: CanonicalGrid, config: ProcessingConfig) -> None:
    aoi = grid.aoi_mask()

    def hrefs(asset: str) -> dict[str, str]:
        return {g.item_id: sign_href(g.assets[asset]) for g in acquisition.granules}

    red = mosaic_band(hrefs("red"), grid, categorical=False)
    nir = mosaic_band(hrefs("nir"), grid, categorical=False)
    scl = mosaic_band(hrefs("scl"), grid, categorical=True)

    baseline = acquisition.processing_baselines[0] if acquisition.processing_baselines else None
    scaling = resolve_band_scaling(None, baseline)

    reflectance_red = to_reflectance(red.values, scaling)
    reflectance_nir = to_reflectance(nir.values, scaling)
    cloud_free = scl_valid_mask(scl.values, config.masked_scl_classes)
    finite = np.isfinite(red.values) & np.isfinite(nir.values)

    as_shipped, valid_px = _mean(
        compute_ndvi(reflectance_red, reflectance_nir, cloud_free & finite)[0],
        cloud_free & finite,
        aoi,
    )
    unmasked, all_px = _mean(compute_ndvi(reflectance_red, reflectance_nir, finite)[0], finite, aoi)

    # Same imagery, same masking — only the additive offset removed.
    no_offset_scaling = BandScaling(scale=scaling.scale, offset=0.0, source="experiment")
    unscaled, _ = _mean(
        compute_ndvi(
            to_reflectance(red.values, no_offset_scaling),
            to_reflectance(nir.values, no_offset_scaling),
            cloud_free & finite,
        )[0],
        cloud_free & finite,
        aoi,
    )

    masked_pct = 100.0 * (all_px - valid_px) / all_px
    print(f"\n  {acquisition.observed_at:%Y-%m-%d}  ({acquisition.granules[0].item_id})")
    print(
        f"    scene-level cloud {acquisition.cloud_cover_pct:.1f}% | "
        f"AOI coverage {acquisition.aoi_coverage_pct:.1f}% | "
        f"baseline {baseline} (offset {scaling.offset}) | "
        f"{masked_pct:.2f}% of AOI masked"
    )
    print(f"    {'as shipped':32s} {as_shipped:8.4f}")
    print(f"    {'cloud masking disabled':32s} {unmasked:8.4f}   ({unmasked - as_shipped:+.4f})")
    print(f"    {'baseline offset ignored':32s} {unscaled:8.4f}   ({unscaled - as_shipped:+.4f})")


def main() -> None:
    config = ProcessingConfig()
    aoi_geojson = dict(mapping(box(*BBOX)))
    grid = CanonicalGrid.from_aoi(aoi_geojson, resolution_m=10.0)

    result = search_scenes(config, BBOX, START, END, MAX_CLOUD_PCT)
    acquisitions = [
        a for a in group_acquisitions(result.candidates, aoi_geojson) if a.aoi_coverage_pct >= 99.0
    ]
    if not acquisitions:
        raise SystemExit("No fully covering acquisitions found.")

    print(f"AOI {BBOX} on {grid.signature()}")
    print(f"{len(acquisitions)} fully covering acquisitions in {START}..{END}")

    # Cloud cover is optional metadata; an acquisition that never reported it
    # must not be selected as the cloudiest one.
    with_cloud = [(a.cloud_cover_pct, a) for a in acquisitions if a.cloud_cover_pct is not None]
    if not with_cloud:
        raise SystemExit("No acquisition reported a cloud percentage.")

    # The extremes bracket the range: if the offset dominates on both the
    # cloudiest and the clearest scene, it is not a cloud artifact.
    measure(max(with_cloud, key=lambda pair: pair[0])[1], grid, config)
    measure(min(with_cloud, key=lambda pair: pair[0])[1], grid, config)


if __name__ == "__main__":
    main()
