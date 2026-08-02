"""API behaviour that requires no database: health, docs, errors, headers."""

from __future__ import annotations


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


def test_datasets_endpoint(client):
    response = client.get("/api/v1/datasets")
    assert response.status_code == 200
    dataset = response.json()[0]
    assert dataset["id"] == "sentinel-2-l2a"
    assert dataset["stac_endpoint"].startswith("https://planetarycomputer.microsoft.com")
    assert dataset["assets_used"]["red"] == "B04"
