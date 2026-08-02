"""Region catalog integrity and queue-message parsing tests."""

from __future__ import annotations

from earth_observation.geometry import bbox_polygon, geodesic_area_km2, validate_bbox
from oeop_core.azure.queue import _parse_content
from oeop_core.regions import load_predefined_regions

MICHIGAN_BBOX = (-90.5, 41.6, -82.1, 48.4)


def test_predefined_regions_are_valid_and_in_michigan():
    regions = load_predefined_regions()
    assert len(regions) >= 3
    slugs = {r["slug"] for r in regions}
    assert "southeast-michigan-demo" in slugs
    for region in regions:
        bbox = validate_bbox(region["bbox"])
        assert MICHIGAN_BBOX[0] <= bbox[0] and bbox[2] <= MICHIGAN_BBOX[2]
        assert MICHIGAN_BBOX[1] <= bbox[1] and bbox[3] <= MICHIGAN_BBOX[3]
        area = geodesic_area_km2(bbox_polygon(bbox))
        assert area < 600, f"Region {region['slug']} too large for demo processing"
        assert area > 1, f"Region {region['slug']} degenerate"


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
