"""Per-acquisition NDVI processing onto the canonical analysis grid.

For each acquisition the pipeline:

1. Signs asset URLs immediately before access (never persisted).
2. Reads only the windows of every contributing granule that intersect the
   canonical grid (COG range reads — full scenes are never downloaded) and
   mosaics them onto that grid: bilinear for spectral bands, nearest for the
   categorical Scene Classification Layer.
3. Verifies geometric AOI coverage against the configured threshold, so an
   acquisition whose granules do not cover the whole AOI is never presented as
   comparable to one that does.
4. Converts digital numbers to reflectance (handling the baseline-04.00
   additive offset), masks contaminated pixels, and computes NDVI.
5. Computes statistics over the canonical AOI mask — identical for every
   observation in the analysis.
6. Writes a float32 NDVI COG, colorized NDVI preview, true-color preview, and
   a per-acquisition summary JSON, all on the canonical grid.

Because step 2 targets the canonical grid directly, every usable observation of
an analysis shares one CRS, transform, width, height, and AOI mask by
construction; masking can change which pixels are valid, never the geometry.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from earth_observation.acquisition import Acquisition
from earth_observation.cog import validate_cog, write_ndvi_cog
from earth_observation.coverage import compute_coverage
from earth_observation.errors import DataError
from earth_observation.grid import CanonicalGrid
from earth_observation.masking import scl_valid_mask
from earth_observation.mosaic import mosaic_band, mosaic_rgb
from earth_observation.ndvi import compute_ndvi, resolve_band_scaling, to_reflectance
from earth_observation.previews import write_ndvi_preview, write_true_color_preview
from earth_observation.stac import sign_href
from earth_observation.stats import compute_scene_stats
from earth_observation.types import (
    AcquisitionSummary,
    ProcessingConfig,
    RasterInfo,
    SceneOutputs,
    SceneResult,
    SceneStats,
)

SignFn = Callable[[str], str]

UNUSABLE_INSUFFICIENT_COVERAGE = "insufficient_aoi_coverage"
UNUSABLE_NO_OVERLAP = "no_raster_overlap_with_aoi"
UNUSABLE_INSUFFICIENT_VALID = "insufficient_valid_pixels"
UNUSABLE_FULLY_MASKED = "all_pixels_masked"


def summarize(acquisition: Acquisition) -> AcquisitionSummary:
    """Serializable identity of an acquisition, including every granule."""
    return AcquisitionSummary(
        key=acquisition.key,
        primary_item_id=acquisition.primary_item_id,
        observed_at=acquisition.observed_at,
        collection=acquisition.collection,
        platform=acquisition.platform,
        relative_orbit=acquisition.relative_orbit,
        cloud_cover_pct=acquisition.cloud_cover_pct,
        contributing_item_ids=acquisition.item_ids,
        tile_ids=acquisition.tile_ids,
        processing_baselines=acquisition.processing_baselines,
        assets={g.item_id: dict(g.assets) for g in acquisition.granules},
    )


def _empty_stats(aoi_pixels: int) -> SceneStats:
    return SceneStats(
        valid_pixel_count=0,
        masked_pixel_count=aoi_pixels,
        aoi_pixel_count=aoi_pixels,
        valid_pixel_pct=0.0,
        zero_denominator_pixel_count=0,
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


def _write_summary(
    path: Path,
    acquisition: Acquisition,
    grid: CanonicalGrid,
    fields: dict[str, Any],
) -> None:
    document = {
        "acquisition_key": acquisition.key,
        "primary_item_id": acquisition.primary_item_id,
        "contributing_item_ids": acquisition.item_ids,
        "tile_ids": acquisition.tile_ids,
        "granule_count": acquisition.granule_count,
        "collection": acquisition.collection,
        "observed_at": acquisition.observed_at.isoformat(),
        "stac_cloud_cover_pct": acquisition.cloud_cover_pct,
        "platform": acquisition.platform,
        "relative_orbit": acquisition.relative_orbit,
        "processing_baselines": acquisition.processing_baselines,
        "source_assets_unsigned": {g.item_id: dict(g.assets) for g in acquisition.granules},
        "canonical_grid": grid.to_dict(),
        **fields,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True))


def process_acquisition(
    acquisition: Acquisition,
    grid: CanonicalGrid,
    config: ProcessingConfig,
    output_dir: Path,
    sign: SignFn = sign_href,
) -> SceneResult:
    """Process one acquisition onto the canonical grid. See module docstring.

    ``sign`` is injected so tests can process local synthetic rasters without
    contacting the Planetary Computer signing endpoint.
    """
    started = time.monotonic()
    warnings: list[str] = list(acquisition.warnings)
    scene_dir = output_dir / acquisition.primary_item_id
    scene_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(acquisition)
    aoi_mask = grid.aoi_mask()
    aoi_pixels = int(np.count_nonzero(aoi_mask))

    def finish(**kwargs: Any) -> SceneResult:
        return SceneResult(
            acquisition=summary,
            processing_seconds=round(time.monotonic() - started, 3),
            warnings=warnings,
            **kwargs,
        )

    def hrefs(role: str) -> dict[str, str]:
        return {g.item_id: sign(g.assets[role]) for g in acquisition.granules if role in g.assets}

    if acquisition.granule_count > 1:
        warnings.append(
            f"AOI spans {acquisition.granule_count} granules "
            f"({', '.join(acquisition.tile_ids)}); mosaicked onto the canonical grid"
        )

    red_band = mosaic_band(hrefs("red"), grid, categorical=False)
    nir_band = mosaic_band(hrefs("nir"), grid, categorical=False)
    scl_band = mosaic_band(hrefs("scl"), grid, categorical=True)

    covered = red_band.covered & nir_band.covered & scl_band.covered
    covered_in_aoi = int(np.count_nonzero(covered & aoi_mask))
    if covered_in_aoi == 0:
        return finish(usable=False, unusable_reason=UNUSABLE_NO_OVERLAP)

    coverage_pct = 100.0 * covered_in_aoi / aoi_pixels if aoi_pixels else 0.0

    scaling = resolve_band_scaling(None, _dominant_baseline(acquisition))
    red_refl = to_reflectance(red_band.values, scaling)
    nir_refl = to_reflectance(nir_band.values, scaling)
    spectral_finite = np.isfinite(red_band.values) & np.isfinite(nir_band.values)

    cloud_free = scl_valid_mask(scl_band.values, config.masked_scl_classes)
    ndvi, zero_denominator = compute_ndvi(red_refl, nir_refl, cloud_free & spectral_finite)
    ndvi[~aoi_mask] = np.nan

    contributing = sorted(
        set(red_band.contributors) | set(nir_band.contributors) | set(scl_band.contributors)
    )
    coverage = compute_coverage(
        aoi_mask=aoi_mask,
        covered=covered,
        scl=scl_band.values,
        masked_classes=config.masked_scl_classes,
        spectral_finite=spectral_finite,
        ndvi_finite=np.isfinite(ndvi),
        granule_count=acquisition.granule_count,
        contributing_item_ids=contributing or acquisition.item_ids,
        tile_ids=acquisition.tile_ids,
    )
    stats = compute_scene_stats(ndvi, aoi_mask, zero_denominator)
    common: dict[str, Any] = {"stats": stats, "coverage": coverage, "scaling": scaling}

    def reject(reason: str) -> SceneResult:
        _write_summary(
            scene_dir / "summary.json",
            acquisition,
            grid,
            {
                "usable": False,
                "unusable_reason": reason,
                "stats": stats.model_dump(),
                "coverage": coverage.model_dump(),
                "band_scaling": scaling.model_dump(),
                "mask_policy_scl_classes": list(config.masked_scl_classes),
                "warnings": warnings,
            },
        )
        return finish(usable=False, unusable_reason=reason, **common)

    # Coverage gate FIRST: an acquisition that does not cover the AOI is not
    # comparable to one that does, however clean its pixels are.
    if coverage_pct < config.min_aoi_coverage_pct:
        warnings.append(
            f"Geometric AOI coverage {coverage_pct:.2f}% is below the required "
            f"{config.min_aoi_coverage_pct:.2f}%"
        )
        return reject(UNUSABLE_INSUFFICIENT_COVERAGE)
    if stats.valid_pixel_count == 0:
        return reject(UNUSABLE_FULLY_MASKED)
    if stats.valid_pixel_pct < config.min_valid_pixel_pct:
        return reject(UNUSABLE_INSUFFICIENT_VALID)

    cog_path = scene_dir / "ndvi.tif"
    write_ndvi_cog(
        cog_path,
        ndvi,
        transform=grid.transform,
        crs=grid.crs,
        nodata=config.output_nodata,
    )
    is_valid, cog_errors, _ = validate_cog(cog_path)
    if not is_valid:
        raise DataError(
            f"Generated COG failed validation for acquisition "
            f"{acquisition.primary_item_id}: {cog_errors}"
        )

    ndvi_png = scene_dir / "ndvi_preview.png"
    write_ndvi_preview(
        ndvi_png,
        ndvi,
        display_min=config.ndvi_display_min,
        display_max=config.ndvi_display_max,
        max_dim=config.preview_max_dim,
        aoi_mask=aoi_mask,
        covered_mask=covered,
    )

    true_color_png = scene_dir / "true_color.png"
    has_true_color = False
    visual_hrefs = hrefs("visual")
    if visual_hrefs:
        rgb = mosaic_rgb(visual_hrefs, grid)
        if rgb is not None:
            write_true_color_preview(
                true_color_png,
                rgb,
                valid_mask=aoi_mask & covered,
                max_dim=config.preview_max_dim,
            )
            has_true_color = True
    if not has_true_color:
        warnings.append("True-color preview unavailable for this acquisition")

    raster_info = RasterInfo(
        crs=grid.crs,
        transform=(
            grid.transform.a,
            grid.transform.b,
            grid.transform.c,
            grid.transform.d,
            grid.transform.e,
            grid.transform.f,
        ),
        width=grid.width,
        height=grid.height,
        resolution=grid.resolution,
        nodata=config.output_nodata,
    )
    summary_path = scene_dir / "summary.json"
    _write_summary(
        summary_path,
        acquisition,
        grid,
        {
            "usable": True,
            "stats": stats.model_dump(),
            "coverage": coverage.model_dump(),
            "band_scaling": scaling.model_dump(),
            "mask_policy_scl_classes": list(config.masked_scl_classes),
            "raster": raster_info.model_dump(),
            "warnings": warnings,
        },
    )

    return finish(
        usable=True,
        raster=raster_info,
        outputs=SceneOutputs(
            ndvi_cog=str(cog_path),
            ndvi_preview=str(ndvi_png),
            true_color_preview=str(true_color_png) if has_true_color else None,
            scene_summary=str(summary_path),
        ),
        **common,
    )


def _dominant_baseline(acquisition: Acquisition) -> str | None:
    """Processing baseline used for reflectance scaling.

    Granules of one acquisition normally share a baseline; when they differ we
    take the lowest (most conservative offset assumption) and the mismatch is
    already recorded as an acquisition warning.
    """
    baselines = acquisition.processing_baselines
    return baselines[0] if baselines else None
