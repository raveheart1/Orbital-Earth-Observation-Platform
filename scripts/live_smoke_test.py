"""Live-data smoke test against the Microsoft Planetary Computer.

Processes ONE real Sentinel-2 scene over a tiny Michigan AOI end to end
(search -> select -> windowed read -> mask -> NDVI -> COG/preview/summary)
and validates the outputs. Requires network access; intentionally NOT part
of the default unit-test suite.

Run:  make live-smoke-test    (or: uv run python scripts/live_smoke_test.py)
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import box, mapping

from earth_observation.cog import validate_cog
from earth_observation.selection import select_scenes
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
    print(f"1/5 Searching {config.collection} for bbox={AOI_BBOX} {START}..{END}")
    candidates = search_scenes(config, AOI_BBOX, START, END, MAX_CLOUD)
    if not candidates:
        fail("No candidate scenes found — try widening the date range")
    print(f"    {len(candidates)} candidates")

    selection = select_scenes(
        candidates,
        scene_limit=1,
        max_cloud_cover_pct=MAX_CLOUD,
        min_aoi_overlap_pct=config.min_aoi_overlap_pct,
        range_start=datetime.fromisoformat(START).replace(tzinfo=UTC),
        range_end=datetime.fromisoformat(END).replace(tzinfo=UTC),
    )
    if not selection.selected:
        fail("Selection produced no scenes")
    scene = selection.selected[0]
    print(
        f"2/5 Selected {scene.item_id} ({scene.observed_at.date()}, cloud {scene.cloud_cover_pct}%)"
    )

    aoi_geojson = dict(mapping(box(*AOI_BBOX)))
    print("3/5 Processing (windowed reads only — no full-scene download)")
    # Imported late so the STAC search above fails fast on network issues.
    from earth_observation.processing import process_scene

    result = process_scene(scene, aoi_geojson, config, OUT_DIR)
    if not result.usable:
        fail(f"Scene unusable: {result.unusable_reason}")
    assert result.stats is not None
    assert result.outputs is not None

    print("4/5 Validating outputs")
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
    summary = json.loads(Path(result.outputs.scene_summary).read_text())
    for key in ("source_assets_unsigned", "band_scaling", "mask_policy_scl_classes", "stats"):
        if key not in summary:
            fail(f"Scene summary missing provenance key: {key}")
    stats = result.stats
    if not (stats.ndvi_mean is not None and -1.0 <= stats.ndvi_mean <= 1.0):
        fail(f"Implausible NDVI mean: {stats.ndvi_mean}")
    if stats.valid_pixel_count <= 0:
        fail("No valid pixels")

    print("5/5 OK")
    print(
        json.dumps(
            {
                "item_id": scene.item_id,
                "observed_at": scene.observed_at.isoformat(),
                "ndvi_mean": round(stats.ndvi_mean, 4),
                "ndvi_median": round(stats.ndvi_median or 0, 4),
                "valid_pixel_pct": stats.valid_pixel_pct,
                "processing_seconds": result.processing_seconds,
                "outputs_dir": str(OUT_DIR),
            },
            indent=2,
        )
    )
    print("PASS: live Planetary Computer smoke test succeeded")


if __name__ == "__main__":
    main()
