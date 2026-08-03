"""Provenance document construction and schema validation."""

from __future__ import annotations

import pytest
from jsonschema import ValidationError
from shapely.geometry import box, mapping

from earth_observation.grid import CanonicalGrid
from earth_observation.processing import summarize
from earth_observation.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    build_provenance,
    validate_provenance,
)
from earth_observation.selection import select_acquisitions
from earth_observation.testing import (
    SELECTION_RANGE_END as END,
)
from earth_observation.testing import (
    SELECTION_RANGE_START as START,
)
from earth_observation.types import ProcessingConfig, SceneResult

from .test_selection import make

AOI = dict(mapping(box(-83.15, 42.30, -83.00, 42.40)))


def _build(results=None, outputs=None):
    config = ProcessingConfig()
    grid = CanonicalGrid.from_aoi(AOI)
    acquisitions = [make("scene-1", 5, 3.0), make("scene-2", 40, 60.0)]
    selection = select_acquisitions(
        acquisitions,
        scene_limit=4,
        max_cloud_cover_pct=20.0,
        min_aoi_coverage_pct=99.0,
        range_start=START,
        range_end=END,
    )
    if results is None:
        results = [
            SceneResult(acquisition=summarize(acquisitions[0]), usable=True, processing_seconds=1.5)
        ]
    if outputs is None:
        outputs = [
            {
                "artifact_type": "timeseries_csv",
                "scene_item_id": None,
                "path": "analyses/x/timeseries.csv",
                "content_type": "text/csv",
                "sha256": "a" * 64,
                "size_bytes": 128,
            }
        ]
    return build_provenance(
        analysis_id="0b2ffb52-6b3c-4b52-a8f7-2e2b3d3a9f10",
        created_at="2024-07-01T00:00:00+00:00",
        config=config,
        grid=grid,
        aoi_geometry=AOI,
        aoi_area_km2=120.5,
        start_date="2024-05-01",
        end_date="2024-09-01",
        max_cloud_cover_pct=20.0,
        scene_limit=4,
        selection=selection,
        results=results,
        outputs=outputs,
        software={
            "processing_version": "2.0.0",
            "git_commit_sha": "deadbeef",
            "container_image": None,
            "python_version": "3.12",
        },
        timing={
            "started_at": "2024-07-01T00:00:00+00:00",
            "completed_at": "2024-07-01T00:05:00+00:00",
            "duration_seconds": 300.0,
        },
    )


def test_document_validates_and_carries_key_fields():
    doc = _build()
    assert doc["schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert doc["scene_selection"]["excluded"][0]["reason"] == "cloud_cover_above_threshold"
    assert doc["processing"]["masked_scl_class_names"][0] == "NO_DATA"
    # Unsigned references persisted, now keyed by contributing item id.
    assert doc["scenes"][0]["assets"]["scene-1"]["red"] == "r"
    assert doc["scenes"][0]["contributing_item_ids"] == ["scene-1"]
    validate_provenance(doc)  # idempotent revalidation


def test_canonical_grid_recorded():
    doc = _build()
    grid = doc["canonical_grid"]
    assert grid["crs"] == "EPSG:32617"
    assert grid["width"] > 0 and grid["height"] > 0
    assert len(grid["transform"]) == 6
    assert len(grid["bounds_projected"]) == 4
    assert grid["signature"].startswith("EPSG:32617")


def test_mosaic_and_resampling_recorded():
    doc = _build()
    processing = doc["processing"]
    assert processing["mosaic_method"] == "first-valid-by-item-id"
    assert processing["resampling_categorical"] == "nearest"
    assert processing["resampling_spectral"] == "bilinear"
    assert doc["scene_selection"]["min_aoi_coverage_pct"] == 99.0


def test_missing_canonical_grid_rejected():
    doc = _build()
    del doc["canonical_grid"]
    with pytest.raises(ValidationError):
        validate_provenance(doc)


def test_bad_checksum_rejected():
    with pytest.raises(ValidationError):
        _build(
            outputs=[
                {
                    "artifact_type": "timeseries_csv",
                    "scene_item_id": None,
                    "path": "p",
                    "content_type": "text/csv",
                    "sha256": "not-a-checksum",
                    "size_bytes": 1,
                }
            ]
        )


def test_missing_required_section_rejected():
    doc = _build()
    del doc["scenes"]
    with pytest.raises(ValidationError):
        validate_provenance(doc)
