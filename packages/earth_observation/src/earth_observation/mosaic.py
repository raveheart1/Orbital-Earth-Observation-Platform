"""Windowed reads and mosaicking onto the canonical grid.

Each contributing granule is read ONLY over the window that intersects the
canonical grid (HTTP range reads against the cloud-optimized assets — full
scenes are never downloaded), then reprojected onto the canonical grid and
merged.

Overlap resolution
------------------
Adjacent Sentinel-2 tiles overlap, and within one acquisition the overlapping
pixels observe the same ground at the same instant, so any consistent choice is
scientifically equivalent. We use **first-valid-by-item-id**: granules are
processed in ascending item-id order and a pixel is filled by the first granule
that supplies data for it. This is deterministic and reproducible, which
matters more than the (negligible) difference between candidates.

Resampling
----------
* Spectral bands (red, NIR) — **bilinear**. Continuous reflectance fields;
  bilinear avoids the aliasing that nearest introduces when the source and
  canonical grids are offset, and it is applied to raw DNs before the NDVI
  ratio, so it does not bias the index. (Cubic was rejected: its overshoot can
  push reflectance outside the physical range near sharp edges such as
  water/land boundaries.)
* Scene Classification Layer — **nearest**, mandatory. SCL values are
  categorical class labels; any averaging would invent classes that do not
  exist (e.g. interpolating cloud=9 and vegetation=4 into water=6).
* True-color preview composite — bilinear (visual product only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from earth_observation.errors import TransientError
from earth_observation.grid import CanonicalGrid

#: GDAL options for efficient HTTP range reads against COGs.
GDAL_ENV: dict[str, str] = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "33554432",
}

#: Extra source pixels read around the window so resampling kernels have
#: neighbours at the edges instead of fabricating them from nodata.
_WINDOW_PAD_PX = 4

MOSAIC_METHOD = "first-valid-by-item-id"
SPECTRAL_RESAMPLING = "bilinear"
CATEGORICAL_RESAMPLING = "nearest"


@dataclass
class MosaicBand:
    """One band mosaicked onto the canonical grid.

    ``values`` is float32 with NaN where no granule supplied data.
    ``covered`` is True where at least one granule's raster grid overlapped the
    pixel, which distinguishes "outside every granule" from "granule nodata".
    ``contributors`` lists the item ids that actually supplied pixels.
    """

    values: npt.NDArray[np.float32]
    covered: npt.NDArray[np.bool_]
    contributors: list[str]


@retry(
    retry=retry_if_exception_type(RasterioIOError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=15),
    reraise=True,
)
def _read_window_onto_grid(
    href: str,
    grid: CanonicalGrid,
    *,
    resampling: Resampling,
    band: int = 1,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.bool_]] | None:
    """Read the granule window covering the grid and reproject it onto the grid.

    Returns ``(values, covered)`` or ``None`` when the granule does not
    intersect the grid at all.
    """
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        src_bounds = transform_bounds(grid.crs, src.crs, *grid.bounds_projected, densify_pts=21)
        window = from_bounds(*src_bounds, transform=src.transform)
        window = window.round_offsets().round_lengths()
        padded = Window(
            window.col_off - _WINDOW_PAD_PX,
            window.row_off - _WINDOW_PAD_PX,
            window.width + 2 * _WINDOW_PAD_PX,
            window.height + 2 * _WINDOW_PAD_PX,
        )
        try:
            read_window = padded.intersection(Window(0, 0, src.width, src.height))
        except rasterio.errors.WindowError:
            return None
        if read_window.width < 1 or read_window.height < 1:
            return None

        data = src.read(band, window=read_window, masked=True)
        if data.size == 0:
            return None
        src_transform = src.window_transform(read_window)

        source = np.ma.filled(data.astype(np.float32), np.nan)
        # Companion mask reprojected the same way tells us which canonical
        # pixels this granule's raster actually reaches (regardless of nodata).
        footprint = np.ones(source.shape, dtype=np.uint8)

        values = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
        reproject(
            source=source,
            destination=values,
            src_transform=src_transform,
            src_crs=src.crs,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=resampling,
        )
        covered = np.zeros((grid.height, grid.width), dtype=np.uint8)
        reproject(
            source=footprint,
            destination=covered,
            src_transform=src_transform,
            src_crs=src.crs,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            src_nodata=0,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
        return values, covered.astype(bool)


def mosaic_band(
    hrefs: dict[str, str],
    grid: CanonicalGrid,
    *,
    categorical: bool,
) -> MosaicBand:
    """Mosaic one band across granules onto the canonical grid.

    ``hrefs`` maps item id -> signed asset href. Granules are consumed in
    ascending item-id order (see module docstring on overlap resolution).
    """
    resampling = Resampling.nearest if categorical else Resampling.bilinear
    values = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    covered = np.zeros((grid.height, grid.width), dtype=bool)
    contributors: list[str] = []

    for item_id in sorted(hrefs):
        try:
            result = _read_window_onto_grid(hrefs[item_id], grid, resampling=resampling)
        except RasterioIOError as exc:
            raise TransientError(
                f"Raster read failed for granule {item_id} after retries: {exc}"
            ) from exc
        if result is None:
            continue
        granule_values, granule_covered = result

        # First-valid-wins: only fill pixels no earlier granule supplied.
        fillable = np.isnan(values) & np.isfinite(granule_values)
        if np.any(fillable):
            values[fillable] = granule_values[fillable]
            contributors.append(item_id)
        covered |= granule_covered

    return MosaicBand(values=values, covered=covered, contributors=contributors)


def mosaic_rgb(hrefs: dict[str, str], grid: CanonicalGrid) -> npt.NDArray[np.uint8] | None:
    """Mosaic a 3-band true-color composite onto the canonical grid."""
    stack = np.full((3, grid.height, grid.width), np.nan, dtype=np.float32)
    filled_any = False
    for item_id in sorted(hrefs):
        for band in (1, 2, 3):
            try:
                result = _read_window_onto_grid(
                    hrefs[item_id], grid, resampling=Resampling.bilinear, band=band
                )
            except (RasterioIOError, IndexError, rasterio.errors.RasterioError):
                return None
            if result is None:
                continue
            values, _ = result
            layer = stack[band - 1]
            fillable = np.isnan(layer) & np.isfinite(values)
            if np.any(fillable):
                layer[fillable] = values[fillable]
                filled_any = True
    if not filled_any:
        return None
    return np.clip(np.nan_to_num(stack, nan=0.0), 0, 255).astype(np.uint8).transpose(1, 2, 0)


def mosaic_metadata() -> dict[str, Any]:
    """Method description recorded in provenance."""
    return {
        "mosaic_method": MOSAIC_METHOD,
        "resampling_spectral": SPECTRAL_RESAMPLING,
        "resampling_categorical": CATEGORICAL_RESAMPLING,
        "window_pad_px": _WINDOW_PAD_PX,
    }
