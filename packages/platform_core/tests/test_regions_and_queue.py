"""Region catalog integrity and queue-message parsing tests."""

from __future__ import annotations

from earth_observation.geometry import bbox_polygon, geodesic_area_km2, validate_bbox
from oeop_core.azure.queue import _parse_content
from oeop_core.regions import load_predefined_regions

MICHIGAN_BBOX = (-90.5, 41.6, -82.1, 48.4)

#: Sentinel-2 observes land roughly between 56S and 83N. A region outside that
#: band would never return imagery, so the catalog must stay inside it.
SENTINEL2_LAT_RANGE = (-56.0, 83.0)


def test_every_region_is_valid_and_within_sentinel2_coverage():
    regions = load_predefined_regions()
    assert len(regions) >= 3
    for region in regions:
        bbox = validate_bbox(region["bbox"])
        assert SENTINEL2_LAT_RANGE[0] <= bbox[1], f"{region['slug']} is south of coverage"
        assert bbox[3] <= SENTINEL2_LAT_RANGE[1], f"{region['slug']} is north of coverage"
        area = geodesic_area_km2(bbox_polygon(bbox))
        assert area < 600, f"Region {region['slug']} too large for demo processing"
        assert area > 1, f"Region {region['slug']} degenerate"


def test_catalog_keeps_a_michigan_focus_and_spans_the_globe():
    """The product is global with a Michigan focus, so the catalog needs both."""
    regions = load_predefined_regions()
    slugs = {r["slug"] for r in regions}
    assert "southeast-michigan-demo" in slugs, "the demonstration region must exist"

    groups = {r["slug"]: r.get("group", "Global") for r in regions}
    michigan = [s for s, g in groups.items() if g == "Michigan"]
    world = [s for s, g in groups.items() if g == "Global"]
    assert len(michigan) >= 3, "Michigan remains the home focus"
    assert len(world) >= 3, "the catalog must demonstrate global reach"

    for region in regions:
        if groups[region["slug"]] != "Michigan":
            continue
        bbox = validate_bbox(region["bbox"])
        assert MICHIGAN_BBOX[0] <= bbox[0] and bbox[2] <= MICHIGAN_BBOX[2]
        assert MICHIGAN_BBOX[1] <= bbox[1] and bbox[3] <= MICHIGAN_BBOX[3]


def test_global_regions_span_multiple_hemispheres_and_utm_zones():
    """Guards the 'works worldwide' claim with the catalog we actually ship."""
    from shapely.geometry import box, mapping

    from earth_observation.grid import CanonicalGrid

    regions = [r for r in load_predefined_regions() if r.get("group") == "Global"]
    lats = [(r["bbox"][1] + r["bbox"][3]) / 2 for r in regions]
    assert any(lat < 0 for lat in lats), "no southern-hemisphere region"
    assert any(lat > 0 for lat in lats), "no northern-hemisphere region"

    zones = set()
    for region in regions:
        grid = CanonicalGrid.from_aoi(dict(mapping(box(*region["bbox"]))), resolution_m=10.0)
        zones.add(grid.epsg)
    assert len(zones) >= 4, f"expected varied UTM zones, got {sorted(zones)}"


def test_every_region_declares_a_group():
    for region in load_predefined_regions():
        assert region.get("group") in {"Michigan", "Global"}, region["slug"]


def test_queue_message_roundtrip_parse():
    analysis_id, enqueued = _parse_content(
        '{"analysis_id": "abc-123", "enqueued_at": "2024-07-01T00:00:00+00:00"}'
    )
    assert analysis_id == "abc-123"
    assert enqueued is not None and enqueued.startswith("2024-07-01")


def test_queue_malformed_message_is_safe():
    analysis_id, enqueued = _parse_content("not json at all")
    assert analysis_id == ""
    assert enqueued is None
