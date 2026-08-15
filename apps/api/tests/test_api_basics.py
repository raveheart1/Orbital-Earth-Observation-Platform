"""API behaviour that requires no database: health, docs, errors, headers."""

from __future__ import annotations

import pytest


def test_liveness(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_schema_generated(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    for expected in (
        "/api/v1/analyses",
        "/api/v1/analyses/{analysis_id}",
        "/api/v1/analyses/{analysis_id}/scenes",
        "/api/v1/analyses/{analysis_id}/timeseries",
        "/api/v1/analyses/{analysis_id}/artifacts",
        "/api/v1/analyses/{analysis_id}/provenance",
        "/api/v1/regions",
        "/api/v1/regions/{region_id}",
        "/api/v1/datasets",
        "/api/v1/config/public",
        "/health/live",
        "/health/ready",
    ):
        assert expected in paths, f"missing path {expected}"


def test_security_headers_present(client):
    response = client.get("/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in response.headers


def test_request_id_propagated(client):
    response = client.get("/health/live", headers={"X-Request-ID": "trace-me-123"})
    assert response.headers["X-Request-ID"] == "trace-me-123"


def test_validation_error_is_problem_json(client):
    response = client.post("/api/v1/analyses", json={"start_date": "not-a-date"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "Request validation failed"
    assert body["status"] == 422
    assert any("end_date" in e["loc"] for e in body["errors"])


def test_unknown_fields_rejected(client):
    response = client.post(
        "/api/v1/analyses",
        json={
            "start_date": "2024-05-01",
            "end_date": "2024-06-01",
            "bbox": [-83.3, 42.5, -83.2, 42.6],
            "blob_path": "../../etc/passwd",
        },
    )
    assert response.status_code == 422


def test_payload_too_large_rejected(client):
    huge = "x" * (70 * 1024)
    response = client.post(
        "/api/v1/analyses",
        content=huge.encode(),
        headers={"Content-Type": "application/json", "Content-Length": str(len(huge))},
    )
    assert response.status_code == 413


def test_public_config_advertises_the_drawn_polygon_vertex_ceiling(client):
    # The web polygon editor discovers the ceiling from /config/public; the
    # endpoint itself needs a database, so the contract is checked via OpenAPI.
    schema = client.get("/openapi.json").json()
    config = schema["components"]["schemas"]["PublicConfigResponse"]["properties"]
    assert config["max_custom_aoi_vertices"]["default"] == 256


def test_unknown_operation_is_invalid_request_problem(client):
    # Rejected before any database access, like the other request validations.
    response = client.post(
        "/api/v1/analyses",
        json={
            "start_date": "2024-05-01",
            "end_date": "2024-06-01",
            "bbox": [-83.3, 42.5, -83.2, 42.6],
            "operation": "ndwi",
        },
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "Invalid analysis request"
    assert body["type"].endswith("#invalid-request")
    assert "'ndwi'" in body["detail"]
    # The detail lists the supported operations so the client can recover.
    assert "ndvi" in body["detail"]
    assert "nbr" in body["detail"]


async def test_public_config_lists_every_registered_operation(test_settings):
    # The endpoint's only database use is the demo-analysis lookup; a stub
    # session reporting "no demo" lets the real handler run otherwise.
    from oeop_api.routers.meta import public_config

    class _EmptyResult:
        def first(self):
            return None

    class _StubSession:
        async def execute(self, *args, **kwargs):
            return _EmptyResult()

    config = await public_config(test_settings, _StubSession())
    operations = {op.id: op for op in config.operations}
    assert set(operations) == {"ndvi", "nbr"}
    ndvi = operations["ndvi"]
    assert ndvi.display_min == pytest.approx(-0.2)
    assert ndvi.display_max == pytest.approx(0.9)
    assert ndvi.change_display_range == pytest.approx(0.4)
    nbr = operations["nbr"]
    assert nbr.display_min == pytest.approx(-1.0)
    assert nbr.display_max == pytest.approx(1.0)
    assert nbr.change_display_range == pytest.approx(0.6)
    assert nbr.title and nbr.description

    # Every operation carries a preview-legend spec matching its colormap, so
    # the web UI never has to label an NBR map with the NDVI legend.
    for op_id, op in operations.items():
        legend = op.legend
        assert legend["type"] == op_id
        assert legend["display_min"] == op.display_min
        assert legend["display_max"] == op.display_max
        assert len(legend["stops"]) > 1
    nbr_stops = operations["nbr"].legend["stops"]
    assert nbr_stops[0]["value"] == pytest.approx(-1.0)
    assert nbr_stops[-1]["value"] == pytest.approx(1.0)

    # Backward compatibility: the legacy top-level field is unchanged.
    assert config.ndvi_legend["type"] == "ndvi"
    assert config.ndvi_legend == operations["ndvi"].legend


def test_datasets_endpoint(client):
    response = client.get("/api/v1/datasets")
    assert response.status_code == 200
    dataset = response.json()[0]
    assert dataset["id"] == "sentinel-2-l2a"
    assert dataset["stac_endpoint"].startswith("https://planetarycomputer.microsoft.com")
    assert dataset["assets_used"]["red"] == "B04"
