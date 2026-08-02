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
        response = httpx.post(
            f"{API}/api/v1/analyses",
            json={
                "bbox": [-85.0, 42.0, -83.0, 44.0],  # ~ tens of thousands of km²
                "start_date": "2024-05-01",
                "end_date": "2024-06-01",
                "max_cloud_cover_pct": 20,
            },
            timeout=10.0,
        )
        assert response.status_code == 422
        assert "exceeds the maximum" in response.json()["detail"]

    def test_submission_validation_rejects_bad_dates(self):
        response = httpx.post(
            f"{API}/api/v1/analyses",
            json={
                "bbox": [-83.25, 42.58, -83.2, 42.62],
                "start_date": "2024-06-01",
                "end_date": "2024-05-01",
                "max_cloud_cover_pct": 20,
            },
            timeout=10.0,
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
