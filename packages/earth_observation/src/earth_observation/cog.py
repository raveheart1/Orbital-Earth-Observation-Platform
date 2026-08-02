"""Cloud Optimized GeoTIFF output and validation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import Affine
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles


def write_ndvi_cog(
    path: Path,
    ndvi: npt.NDArray[np.float32],
    *,
    transform: Affine,
    crs: str,
    nodata: float,
) -> None:
    """Write a float32 NDVI array (NaN = invalid) as a deflate-compressed COG.

    NaN is converted to the explicit ``nodata`` value so downstream tools that
    mishandle NaN nodata still read the raster correctly.
    """
    data = np.where(np.isfinite(ndvi), ndvi, np.float32(nodata)).astype(np.float32)
    src_profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": data.shape[0],
        "width": data.shape[1],
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
    }
    dst_profile = cog_profiles.get("deflate")  # type: ignore[no-untyped-call]
    path.parent.mkdir(parents=True, exist_ok=True)
    with MemoryFile() as memfile:
        with memfile.open(**src_profile) as mem:
            mem.write(data, 1)
        cog_translate(
            memfile.name,
            str(path),
            dst_profile,
            in_memory=True,
            quiet=True,
        )


def validate_cog(path: Path) -> tuple[bool, list[str], list[str]]:
    """Structurally validate a COG. Returns (is_valid, errors, warnings)."""
    is_valid, errors, warnings = cog_validate(str(path), quiet=True)
    return bool(is_valid), list(errors), list(warnings)


def read_raster_info(path: Path) -> dict[str, object]:
    """Georeferencing summary of a written raster, for provenance."""
    with rasterio.open(path) as src:
        return {
            "crs": str(src.crs),
            "transform": tuple(src.transform)[:6],
            "width": src.width,
            "height": src.height,
            "resolution": (abs(src.transform.a), abs(src.transform.e)),
            "nodata": src.nodata,
            "dtype": src.dtypes[0],
        }
