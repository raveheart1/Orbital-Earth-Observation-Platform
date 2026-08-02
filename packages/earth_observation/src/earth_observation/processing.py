"""Per-scene NDVI processing pipeline.

For each selected scene the pipeline:

1. Signs asset URLs immediately before access (never persisted).
2. Reads only the raster window covering the AOI from the cloud-optimized
   assets (GDAL range reads — full scenes are never downloaded).
3. Aligns the 20 m Scene Classification Layer to the 10 m band grid with
   nearest-neighbour resampling (preserves class labels).
4. Converts digital numbers to reflectance (handling the baseline-04.00
   additive offset), masks contaminated pixels, and computes NDVI.
5. Clips to the exact AOI geometry and computes statistics over valid pixels.
6. Writes a float32 NDVI COG, colorized NDVI preview, true-color preview,
   and a per-scene summary JSON.

Processing happens in the scene's native UTM CRS: the AOI is small, so
keeping the source grid avoids an unnecessary resampling step; per-scene
scalar statistics are unaffected by scenes falling in different UTM zones.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rioxarray
import xarray as xr
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.features import geometry_mask
from rioxarray.exceptions import NoDataInBounds, OneDimensionalRaster
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from earth_observation.cog import validate_cog, write_ndvi_cog
from earth_observation.errors import DataError, TransientError
from earth_observation.masking import scl_valid_mask
from earth_observation.ndvi import compute_ndvi, resolve_band_scaling, to_reflectance
from earth_observation.previews import write_ndvi_preview, write_true_color_preview
from earth_observation.stac import sign_href
from earth_observation.stats import compute_scene_stats
from earth_observation.types import (
    ProcessingConfig,
    RasterInfo,
    SceneCandidate,
    SceneOutputs,
    SceneResult,
    SceneStats,
)

#: GDAL options for efficient HTTP range reads against COGs.
GDAL_ENV: dict[str, str] = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "33554432",
}

#: Padding (in source-CRS units, meters for UTM) added around the AOI window
#: so masking and clipping have full pixel coverage at the edges.
_CLIP_PAD_M = 40.0

SignFn = Callable[[str], str]

_UNUSABLE_NO_OVERLAP = "no_raster_overlap_with_aoi"
_UNUSABLE_INSUFFICIENT_VALID = "insufficient_valid_pixels"
_UNUSABLE_FULLY_MASKED = "all_pixels_masked"


@retry(
    retry=retry_if_exception_type(RasterioIOError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=15),
    reraise=True,
)
def _open_clipped(
    href: str,
    bounds: tuple[float, float, float, float],
    *,
    masked: bool,
) -> xr.DataArray:
    """Open a raster asset and clip it to ``bounds`` (asset CRS) via range reads."""
    with rasterio.Env(**GDAL_ENV):
        da = rioxarray.open_rasterio(href, masked=masked)
        assert isinstance(da, xr.DataArray)
        clipped: xr.DataArray = da.rio.clip_box(*bounds)
        clipped.load()
        da.close()
        return clipped


def _aoi_in_scene_crs(aoi_geojson: dict[str, Any], epsg: int) -> Any:
    aoi = shape(aoi_geojson)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    return shapely_transform(transformer.transform, aoi)


def _grids_match(a: xr.DataArray, b: xr.DataArray) -> bool:
    return bool(
        a.rio.shape == b.rio.shape
        and a.rio.transform() == b.rio.transform()
        and a.rio.crs == b.rio.crs
    )


def _empty_stats(aoi_pixels: int, zero_denominator: int = 0) -> SceneStats:
    return SceneStats(
        valid_pixel_count=0,
        masked_pixel_count=aoi_pixels,
        aoi_pixel_count=aoi_pixels,
        valid_pixel_pct=0.0,
        zero_denominator_pixel_count=zero_denominator,
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


def _detect_epsg(candidate: SceneCandidate, sign: SignFn) -> int:
    """Use the STAC projection metadata, falling back to reading the asset header."""
    if candidate.epsg is not None:
        return candidate.epsg
    with rasterio.Env(**GDAL_ENV), rasterio.open(sign(candidate.assets["red"])) as src:
        epsg = src.crs.to_epsg()
    if epsg is None:
        raise DataError(f"Cannot determine CRS for scene {candidate.item_id}")
    return int(epsg)


def _write_scene_summary(
    path: Path,
    candidate: SceneCandidate,
    result_fields: dict[str, Any],
) -> None:
    document = {
        "item_id": candidate.item_id,
        "collection": candidate.collection,
        "observed_at": candidate.observed_at.isoformat(),
        "stac_cloud_cover_pct": candidate.cloud_cover_pct,
        "platform": candidate.platform,
        "instruments": candidate.instruments,
        "processing_baseline": candidate.processing_baseline,
        "source_assets_unsigned": candidate.assets,
        **result_fields,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True))


def _true_color_preview(
    candidate: SceneCandidate,
    bounds: tuple[float, float, float, float],
    aoi_mask: np.ndarray,
    red_grid: xr.DataArray,
    out_path: Path,
    config: ProcessingConfig,
    sign: SignFn,
    warnings: list[str],
) -> bool:
    """Render the source-provided true-color (TCI) asset for the AOI window."""
    visual_href = candidate.assets.get("visual")
    if visual_href is None:
        warnings.append("Scene has no true-color (visual) asset; preview skipped")
        return False
    try:
        visual = _open_clipped(sign(visual_href), bounds, masked=False)
    except (RasterioIOError, NoDataInBounds, OneDimensionalRaster) as exc:
        warnings.append(f"True-color preview unavailable: {type(exc).__name__}")
        return False
    try:
        if not _grids_match(visual, red_grid):
            visual = visual.rio.reproject_match(red_grid, resampling=Resampling.bilinear)
        data = np.asarray(visual.values)
        if data.shape[0] < 3:
            warnings.append("Visual asset has fewer than 3 bands; preview skipped")
            return False
        rgb = np.clip(data[:3], 0, 255).astype(np.uint8).transpose(1, 2, 0)
        write_true_color_preview(out_path, rgb, valid_mask=aoi_mask, max_dim=config.preview_max_dim)
        return True
    finally:
        visual.close()


def process_scene(
    candidate: SceneCandidate,
    aoi_geojson: dict[str, Any],
    config: ProcessingConfig,
    output_dir: Path,
    sign: SignFn = sign_href,
) -> SceneResult:
    """Run the full per-scene pipeline; see module docstring.

    ``sign`` is injected so tests can process local synthetic rasters without
    contacting the Planetary Computer signing endpoint.
    """
    started = time.monotonic()
    warnings: list[str] = []
    scene_dir = output_dir / candidate.item_id
    scene_dir.mkdir(parents=True, exist_ok=True)

    def finish(**kwargs: Any) -> SceneResult:
        return SceneResult(
            candidate=candidate,
            processing_seconds=round(time.monotonic() - started, 3),
            warnings=warnings,
            **kwargs,
        )

    epsg = _detect_epsg(candidate, sign)
    aoi_scene = _aoi_in_scene_crs(aoi_geojson, epsg)
    minx, miny, maxx, maxy = aoi_scene.bounds
    bounds = (minx - _CLIP_PAD_M, miny - _CLIP_PAD_M, maxx + _CLIP_PAD_M, maxy + _CLIP_PAD_M)

    try:
        red = _open_clipped(sign(candidate.assets["red"]), bounds, masked=True)
        nir = _open_clipped(sign(candidate.assets["nir"]), bounds, masked=True)
        scl = _open_clipped(sign(candidate.assets["scl"]), bounds, masked=True)
    except (NoDataInBounds, OneDimensionalRaster):
        return finish(usable=False, unusable_reason=_UNUSABLE_NO_OVERLAP)
    except RasterioIOError as exc:
        raise TransientError(
            f"Raster read failed for scene {candidate.item_id} after retries: {exc}"
        ) from exc

    # Align everything to the red 10 m grid.
    if not _grids_match(nir, red):
        warnings.append("NIR grid differed from red grid; reprojected to match")
        nir = nir.rio.reproject_match(red, resampling=Resampling.bilinear)
    scl = scl.rio.reproject_match(red, resampling=Resampling.nearest)

    red2d = np.asarray(red.squeeze("band", drop=True).values, dtype=np.float64)
    nir2d = np.asarray(nir.squeeze("band", drop=True).values, dtype=np.float64)
    scl2d = np.asarray(scl.squeeze("band", drop=True).values)

    # Exact-AOI footprint mask on the processing grid.
    grid_transform = red.rio.transform()
    aoi_mask = geometry_mask(
        [aoi_scene],
        out_shape=red2d.shape,
        transform=grid_transform,
        invert=True,
    )
    aoi_pixels = int(np.count_nonzero(aoi_mask))
    if aoi_pixels == 0:
        return finish(usable=False, unusable_reason=_UNUSABLE_NO_OVERLAP)

    scaling = resolve_band_scaling(None, candidate.processing_baseline)
    red_refl = to_reflectance(red2d, scaling)
    nir_refl = to_reflectance(nir2d, scaling)

    cloud_free = scl_valid_mask(scl2d, config.masked_scl_classes)
    ndvi, zero_denominator = compute_ndvi(red_refl, nir_refl, cloud_free)
    ndvi[~aoi_mask] = np.nan

    stats = compute_scene_stats(ndvi, aoi_mask, zero_denominator)
    result_common: dict[str, Any] = {"stats": stats, "scaling": scaling}

    if stats.valid_pixel_count == 0:
        _write_scene_summary(
            scene_dir / "summary.json",
            candidate,
            {
                "usable": False,
                "unusable_reason": _UNUSABLE_FULLY_MASKED,
                "stats": stats.model_dump(),
                "band_scaling": scaling.model_dump(),
                "mask_policy_scl_classes": list(config.masked_scl_classes),
            },
        )
        return finish(usable=False, unusable_reason=_UNUSABLE_FULLY_MASKED, **result_common)
    if stats.valid_pixel_pct < config.min_valid_pixel_pct:
        _write_scene_summary(
            scene_dir / "summary.json",
            candidate,
            {
                "usable": False,
                "unusable_reason": _UNUSABLE_INSUFFICIENT_VALID,
                "stats": stats.model_dump(),
                "band_scaling": scaling.model_dump(),
                "mask_policy_scl_classes": list(config.masked_scl_classes),
            },
        )
        return finish(usable=False, unusable_reason=_UNUSABLE_INSUFFICIENT_VALID, **result_common)

    # Outputs.
    cog_path = scene_dir / "ndvi.tif"
    write_ndvi_cog(
        cog_path,
        ndvi,
        transform=grid_transform,
        crs=f"EPSG:{epsg}",
        nodata=config.output_nodata,
    )
    is_valid, cog_errors, _cog_warnings = validate_cog(cog_path)
    if not is_valid:
        raise DataError(
            f"Generated COG failed validation for scene {candidate.item_id}: {cog_errors}"
        )

    ndvi_png = scene_dir / "ndvi_preview.png"
    write_ndvi_preview(
        ndvi_png,
        ndvi,
        display_min=config.ndvi_display_min,
        display_max=config.ndvi_display_max,
        max_dim=config.preview_max_dim,
    )

    true_color_png = scene_dir / "true_color.png"
    has_true_color = _true_color_preview(
        candidate, bounds, aoi_mask, red, true_color_png, config, sign, warnings
    )

    raster_info = RasterInfo(
        crs=f"EPSG:{epsg}",
        transform=tuple(grid_transform)[:6],  # type: ignore[arg-type]
        width=ndvi.shape[1],
        height=ndvi.shape[0],
        resolution=(abs(grid_transform.a), abs(grid_transform.e)),
        nodata=config.output_nodata,
    )
    summary_path = scene_dir / "summary.json"
    _write_scene_summary(
        summary_path,
        candidate,
        {
            "usable": True,
            "stats": stats.model_dump(),
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
        **result_common,
    )
