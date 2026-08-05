"""Integration tests against the running local stack (API on localhost:8000).

Run with the stack up (``make dev && make migrate && make seed``):

    uv run pytest tests -m integration

Skipped automatically when the API is unreachable, so the default suite stays
service-free.
"""

from __future__ import annotations

import httpx
import pytest

API = "http://localhost:8000"

pytestmark = pytest.mark.integration


def _api_available() -> bool:
    try:
        return httpx.get(f"{API}/health/live", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


requires_stack = pytest.mark.skipif(not _api_available(), reason="local API stack is not running")


def submit(payload: dict, timeout: float = 15.0) -> httpx.Response:
    """POST an analysis, skipping the test if the submission throttle trips.

    The per-client rate limit is real production behaviour, but these tests are
    about validation. A 429 means we never got to exercise validation, so skip
    rather than report a false failure.
    """
    response = httpx.post(f"{API}/api/v1/analyses", json=payload, timeout=timeout)
    if response.status_code == 429:
        pytest.skip("submission rate limit reached; restart the API to reset it")
    return response


@requires_stack
class TestLocalStack:
    def test_readiness_reports_dependencies(self):
        response = httpx.get(f"{API}/health/ready", timeout=10.0)
        assert response.status_code == 200
        body = response.json()
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["queue"] == "ok"

    def test_regions_seeded(self):
        response = httpx.get(f"{API}/api/v1/regions", timeout=10.0)
        assert response.status_code == 200
        slugs = {r["slug"] for r in response.json()}
        assert "southeast-michigan-demo" in slugs
        assert len(slugs) >= 3

    def test_submission_validation_rejects_oversized_aoi(self):
        response = submit(
            {
                "bbox": [-85.0, 42.0, -83.0, 44.0],  # ~ tens of thousands of km²
                "start_date": "2024-05-01",
                "end_date": "2024-06-01",
                "max_cloud_cover_pct": 20,
            }
        )
        assert response.status_code == 422
        assert "exceeds the maximum" in response.json()["detail"]

    def test_submission_validation_rejects_bad_dates(self):
        response = submit(
            {
                "bbox": [-83.05, 42.33, -83.0388, 42.3388],
                "start_date": "2024-06-01",
                "end_date": "2024-05-01",
                "max_cloud_cover_pct": 20,
            }
        )
        assert response.status_code == 422

    def test_analysis_lifecycle_endpoints(self):
        """Whatever analyses exist must serialize consistently."""
        listing = httpx.get(f"{API}/api/v1/analyses", timeout=10.0).json()
        assert {"items", "total", "limit", "offset"} <= set(listing)
        for item in listing["items"][:3]:
            detail = httpx.get(f"{API}{item['links']['self']}", timeout=10.0)
            assert detail.status_code == 200
            assert detail.json()["id"] == item["id"]
            scenes = httpx.get(f"{API}{item['links']['scenes']}", timeout=10.0)
            assert scenes.status_code == 200

    def test_openapi_served(self):
        response = httpx.get(f"{API}/openapi.json", timeout=10.0)
        assert response.status_code == 200
        assert response.json()["info"]["title"].startswith("Orbital")


@requires_stack
class TestCustomAreaSubmission:
    """The 2 km² cap is enforced server-side, not just in the browser."""

    def test_public_config_advertises_the_custom_area_limit(self):
        config = httpx.get(f"{API}/api/v1/config/public", timeout=10.0).json()
        assert config["custom_areas_enabled"] is True
        assert 0 < config["max_custom_aoi_area_km2"] < config["max_aoi_area_km2"]

    def test_oversized_drawn_box_is_rejected(self):
        """Above the custom cap a drawn area must fail, however it was drawn."""
        response = submit(
            {
                # ~1,900 km², comfortably above the 250 km² custom ceiling.
                "bbox": [-83.6, 42.1, -83.0, 42.6],
                "start_date": "2024-06-01",
                "end_date": "2024-08-31",
                "max_cloud_cover_pct": 20,
            }
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "custom areas" in detail.lower()
        assert "predefined region" in detail.lower()

    def test_region_sized_drawn_box_is_now_accepted(self):
        """The cap was raised to 250 km², so a region-sized drawn box is legal."""
        response = submit(
            {
                "bbox": [-83.15, 42.30, -83.00, 42.40],  # ~137 km²
                "start_date": "2024-06-01",
                "end_date": "2024-08-31",
                "max_cloud_cover_pct": 20,
                "scene_limit": 1,
            }
        )
        assert response.status_code == 202
        assert response.json()["area_km2"] < 250.0

    def test_small_drawn_box_is_accepted(self):
        response = submit(
            {
                "bbox": [-83.05, 42.33, -83.0388, 42.3388],  # ~0.9 km²
                "start_date": "2024-06-01",
                "end_date": "2024-08-31",
                "max_cloud_cover_pct": 20,
                "scene_limit": 2,
            }
        )
        assert response.status_code == 202
        body = response.json()
        assert body["region"] is None
        assert body["area_km2"] < 2.0

    def test_predefined_region_still_allows_a_large_area(self):
        """The tight custom cap must not break region submissions."""
        regions = httpx.get(f"{API}/api/v1/regions", timeout=10.0).json()
        region = next(r for r in regions if r["slug"] == "detroit-urban-core")
        assert region["area_km2"] > 2.0
        response = submit(
            {
                "region_id": region["id"],
                "start_date": "2024-06-01",
                "end_date": "2024-08-31",
                "max_cloud_cover_pct": 20,
                "scene_limit": 1,
            }
        )
        assert response.status_code == 202
