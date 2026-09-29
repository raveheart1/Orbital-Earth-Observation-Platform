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


def write_class_cog(
    path: Path,
    classes: npt.NDArray[np.integer],
    *,
    transform: Affine,
    crs: str,
    nodata: int = 0,
) -> None:
    """Write a CATEGORICAL uint8 raster (class codes) as a deflate COG.

    Overviews are built with NEAREST resampling: averaging class codes would
    invent classes that do not exist (the same rule that governs SCL and
    land-cover reprojection).
    """
    data = np.asarray(classes).astype(np.uint8)
    src_profile = {
        "driver": "GTiff",
        "dtype": "uint8",
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
            overview_resampling="nearest",
        )


def read_class_array(path: Path) -> npt.NDArray[np.uint8]:
    """Read a single-band categorical raster written by :func:`write_class_cog`."""
    with rasterio.open(path) as src:
        return np.asarray(src.read(1), dtype=np.uint8)


def read_ndvi_array(path: Path) -> npt.NDArray[np.float32]:
    """Read a single-band float32 raster back into the NaN-is-invalid convention.

    Inverse of :func:`write_ndvi_cog`: pixels carrying the file's explicit
    nodata value come back as NaN.
    """
    with rasterio.open(path) as src:
        data = np.asarray(src.read(1), dtype=np.float32)
        nodata = src.nodata
    if nodata is not None:
        data[data == np.float32(nodata)] = np.nan
    return data


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
