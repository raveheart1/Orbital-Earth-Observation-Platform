"""Analysis-level time-series and summary outputs.

Observation dates are reported exactly as observed — missing dates are never
interpolated. The CSV column order is part of the public artifact contract.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from earth_observation.types import SceneResult

TIMESERIES_COLUMNS = [
    "acquisition_key",
    "primary_item_id",
    "contributing_item_ids",
    "tile_ids",
    "granule_count",
    "observed_at",
    "stac_cloud_cover_pct",
    "aoi_coverage_pct",
    "valid_coverage_pct",
    "missing_data_pct",
    "valid_pixel_count",
    "masked_pixel_count",
    "valid_pixel_pct",
    "ndvi_min",
    "ndvi_max",
    "ndvi_mean",
    "ndvi_median",
    "ndvi_std",
    "ndvi_p10",
    "ndvi_p25",
    "ndvi_p75",
    "ndvi_p90",
]


def timeseries_rows(results: list[SceneResult]) -> list[dict[str, Any]]:
    """Rows for usable scenes only, chronologically sorted."""
    rows: list[dict[str, Any]] = []
    for result in sorted(results, key=lambda r: r.acquisition.observed_at):
        if not result.usable or result.stats is None:
            continue
        stats = result.stats
        coverage = result.coverage
        rows.append(
            {
                "acquisition_key": result.acquisition.key,
                "primary_item_id": result.acquisition.primary_item_id,
                "contributing_item_ids": " ".join(result.acquisition.contributing_item_ids),
                "tile_ids": " ".join(result.acquisition.tile_ids),
                "granule_count": len(result.acquisition.contributing_item_ids),
                "observed_at": result.acquisition.observed_at.isoformat(),
                "stac_cloud_cover_pct": result.acquisition.cloud_cover_pct,
                "aoi_coverage_pct": coverage.aoi_coverage_pct if coverage else None,
                "valid_coverage_pct": coverage.valid_coverage_pct if coverage else None,
                "missing_data_pct": coverage.missing_data_pct if coverage else None,
                "valid_pixel_count": stats.valid_pixel_count,
                "masked_pixel_count": stats.masked_pixel_count,
                "valid_pixel_pct": stats.valid_pixel_pct,
                "ndvi_min": stats.ndvi_min,
                "ndvi_max": stats.ndvi_max,
                "ndvi_mean": stats.ndvi_mean,
                "ndvi_median": stats.ndvi_median,
                "ndvi_std": stats.ndvi_std,
                "ndvi_p10": stats.ndvi_p10,
                "ndvi_p25": stats.ndvi_p25,
                "ndvi_p75": stats.ndvi_p75,
                "ndvi_p90": stats.ndvi_p90,
            }
        )
    return rows


def write_timeseries_csv(path: Path, results: list[SceneResult]) -> int:
    """Write the analysis time series as CSV; returns the row count."""
    rows = timeseries_rows(results)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMESERIES_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def analysis_summary(results: list[SceneResult]) -> dict[str, Any]:
    """Aggregate summary across usable scenes; safe when nothing was usable."""
    usable = [r for r in results if r.usable and r.stats is not None]
    unusable = [r for r in results if not r.usable]
    if not usable:
        return {
            "usable_scene_count": 0,
            "unusable_scene_count": len(unusable),
            "first_observation": None,
            "last_observation": None,
            "ndvi_mean_first": None,
            "ndvi_mean_last": None,
            "ndvi_mean_change": None,
            "mean_valid_pixel_pct": None,
        }
    ordered = sorted(usable, key=lambda r: r.acquisition.observed_at)
    first, last = ordered[0], ordered[-1]
    assert first.stats is not None
    assert last.stats is not None
    means = [r.stats.valid_pixel_pct for r in ordered if r.stats is not None]
    change: float | None = None
    if first.stats.ndvi_mean is not None and last.stats.ndvi_mean is not None:
        change = last.stats.ndvi_mean - first.stats.ndvi_mean
    coverages = [r.coverage.aoi_coverage_pct for r in ordered if r.coverage is not None]
    grids = {r.raster.crs + f":{r.raster.width}x{r.raster.height}" for r in ordered if r.raster}
    return {
        "usable_scene_count": len(usable),
        "unusable_scene_count": len(unusable),
        "first_observation": first.acquisition.observed_at.isoformat(),
        "last_observation": last.acquisition.observed_at.isoformat(),
        "ndvi_mean_first": first.stats.ndvi_mean,
        "ndvi_mean_last": last.stats.ndvi_mean,
        "ndvi_mean_change": change,
        "mean_valid_pixel_pct": sum(means) / len(means) if means else None,
        "min_aoi_coverage_pct": min(coverages) if coverages else None,
        "identical_analytical_grid": len(grids) <= 1,
        "comparison_note": (
            "Every observation above was computed on one canonical grid over "
            "the identical AOI footprint, so the change between dates reflects "
            "the same ground."
        ),
        "interpretation_note": (
            "Values are observed spectral vegetation-index changes for the "
            "specific acquisition dates shown. They do not by themselves "
            "establish causes such as drought, land-use change, or climate "
            "trends. See the limitations documentation."
        ),
    }
