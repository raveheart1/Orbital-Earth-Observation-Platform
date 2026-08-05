"""Live-data smoke test against the Microsoft Planetary Computer.

Processes ONE real Sentinel-2 acquisition over a tiny Michigan AOI end to end
(search -> group -> select -> canonical grid -> windowed mosaic -> mask ->
NDVI -> COG/preview/summary) and validates the outputs. Requires network
access; intentionally NOT part of the default unit-test suite.

Run:  make live-smoke-test    (or: uv run python scripts/live_smoke_test.py)
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import box, mapping

from earth_observation.acquisition import group_acquisitions
from earth_observation.cog import validate_cog
from earth_observation.grid import CanonicalGrid
from earth_observation.selection import select_acquisitions
from earth_observation.stac import search_scenes
from earth_observation.types import ProcessingConfig

#: Tiny AOI in the Southeast Michigan demonstration region (~15 km^2).
AOI_BBOX = (-83.25, 42.58, -83.20, 42.62)
START, END = "2024-06-01", "2024-08-31"
MAX_CLOUD = 15.0
OUT_DIR = Path("data/local/live-smoke")


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def main() -> None:
    config = ProcessingConfig(preview_max_dim=512)
    aoi_geojson = dict(mapping(box(*AOI_BBOX)))

    print(f"1/6 Searching {config.collection} for bbox={AOI_BBOX} {START}..{END}")
    search = search_scenes(config, AOI_BBOX, START, END, MAX_CLOUD)
    candidates = search.candidates
    if not candidates:
        fail("No candidate granules found — try widening the date range")
    print(f"    {len(candidates)} granules across {len(search.windows)} search window(s)")
    if search.truncated:
        print(f"    WARNING: truncated windows {search.truncated_windows}")

    print("2/6 Grouping granules into acquisitions")
    acquisitions = group_acquisitions(candidates, aoi_geojson)
    multi = [a for a in acquisitions if a.granule_count > 1]
    print(f"    {len(acquisitions)} acquisitions ({len(multi)} span multiple granules)")

    selection = select_acquisitions(
        acquisitions,
        scene_limit=1,
        max_cloud_cover_pct=MAX_CLOUD,
        min_aoi_coverage_pct=config.min_aoi_coverage_pct,
        range_start=datetime.fromisoformat(START).replace(tzinfo=UTC),
        range_end=datetime.fromisoformat(END).replace(tzinfo=UTC),
    )
    if not selection.selected:
        fail(
            "Selection produced no acquisition covering at least "
            f"{config.min_aoi_coverage_pct}% of the AOI"
        )
    acquisition = selection.selected[0]
    print(
        f"3/6 Selected {acquisition.primary_item_id} "
        f"({acquisition.observed_at.date()}, cloud {acquisition.cloud_cover_pct}%, "
        f"{acquisition.granule_count} granule(s) {acquisition.tile_ids}, "
        f"AOI coverage {acquisition.aoi_coverage_pct:.2f}%)"
    )

    grid = CanonicalGrid.from_aoi(aoi_geojson, resolution_m=config.grid_resolution_m)
    print(f"4/6 Canonical grid {grid.crs} {grid.width}x{grid.height} @ {grid.resolution[0]} m")

    print("5/6 Processing (windowed reads only — no full-scene download)")
    # Imported late so the STAC search above fails fast on network issues.
    from earth_observation.processing import process_acquisition

    result = process_acquisition(acquisition, grid, config, OUT_DIR)
    if not result.usable:
        fail(f"Acquisition unusable: {result.unusable_reason}")
    assert result.stats is not None
    assert result.outputs is not None
    assert result.coverage is not None
    assert result.raster is not None

    print("6/6 Validating outputs")
    is_valid, errors, _ = validate_cog(Path(result.outputs.ndvi_cog))
    if not is_valid:
        fail(f"COG validation failed: {errors}")
    for path in (
        result.outputs.ndvi_cog,
        result.outputs.ndvi_preview,
        result.outputs.scene_summary,
    ):
        if not Path(path).exists():
            fail(f"Missing output: {path}")

    # The output must land on the canonical grid exactly — this is what makes
    # observations of one analysis comparable.
    if (result.raster.width, result.raster.height) != (grid.width, grid.height):
        fail(
            f"Output {result.raster.width}x{result.raster.height} does not match "
            f"the canonical grid {grid.width}x{grid.height}"
        )
    if result.raster.crs != grid.crs:
        fail(f"Output CRS {result.raster.crs} does not match the grid {grid.crs}")

    summary = json.loads(Path(result.outputs.scene_summary).read_text())
    for key in (
        "source_assets_unsigned",
        "band_scaling",
        "mask_policy_scl_classes",
        "stats",
        "coverage",
        "canonical_grid",
        "contributing_item_ids",
    ):
        if key not in summary:
            fail(f"Scene summary missing provenance key: {key}")

    stats = result.stats
    if stats.ndvi_mean is None or not (-1.0 <= stats.ndvi_mean <= 1.0):
        fail(f"Implausible NDVI mean: {stats.ndvi_mean}")
        return  # unreachable; narrows ndvi_mean to float for the checks below
    if stats.valid_pixel_count <= 0:
        fail("No valid pixels")
    if stats.aoi_pixel_count != grid.aoi_pixel_count():
        fail("Statistics were not computed over the canonical AOI mask")

    print(
        json.dumps(
            {
                "acquisition_key": acquisition.key,
                "contributing_item_ids": result.coverage.contributing_item_ids,
                "tile_ids": result.coverage.tile_ids,
                "observed_at": acquisition.observed_at.isoformat(),
                "grid": grid.signature(),
                "aoi_coverage_pct": result.coverage.aoi_coverage_pct,
                "valid_pixel_pct": stats.valid_pixel_pct,
                "ndvi_mean": round(stats.ndvi_mean, 4),
                "ndvi_median": round(stats.ndvi_median or 0, 4),
                "processing_seconds": result.processing_seconds,
                "outputs_dir": str(OUT_DIR),
            },
            indent=2,
        )
    )
    print("PASS: live Planetary Computer smoke test succeeded")


if __name__ == "__main__":
    main()
