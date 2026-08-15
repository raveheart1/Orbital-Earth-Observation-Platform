"""Provenance document construction and schema validation."""

from __future__ import annotations

import pytest
from jsonschema import ValidationError
from shapely.geometry import box, mapping

from earth_observation.grid import CanonicalGrid
from earth_observation.indices import INDICES
from earth_observation.previews import change_legend_spec
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


def _build(results=None, outputs=None, change=None, index=None, fire_context=None):
    config = ProcessingConfig()
    index = INDICES["ndvi"] if index is None else index
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
        index=index,
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
        change=change,
        fire_context=fire_context,
    )


def _change_block():
    return {
        "computed": True,
        "operation": "ndvi",
        "earlier": {"stac_item_id": "scene-1", "observed_at": "2024-05-06T00:00:00+00:00"},
        "later": {"stac_item_id": "scene-2", "observed_at": "2024-06-10T00:00:00+00:00"},
        "mask_policy": "valid_in_both",
        "delta_threshold": 0.1,
        "display_range": 0.4,
        "colormap_stops": change_legend_spec(0.4)["stops"],
        "stats": {"valid_both_pct": 92.1},
    }


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


def test_change_block_validates_and_is_optional():
    doc = _build(change=_change_block())
    assert doc["change"]["mask_policy"] == "valid_in_both"
    assert doc["change"]["colormap_stops"][3]["value"] == 0.0
    validate_provenance(doc)
    # Documents without a change map (e.g. one usable observation) still validate.
    assert "change" not in _build()


def test_change_skip_reason_validates():
    doc = _build(change={"computed": False, "skipped_reason": "fewer_than_two_usable_observations"})
    assert doc["change"]["computed"] is False
    validate_provenance(doc)


def test_change_with_wrong_mask_policy_rejected():
    bad = _change_block()
    bad["mask_policy"] = "valid_in_either"
    with pytest.raises(ValidationError):
        _build(change=bad)


def test_index_identity_recorded():
    """Schema 2.2.0: the processing block names the index, its formula, bands."""
    doc = _build()
    processing = doc["processing"]
    assert processing["operation"] == "ndvi"
    index = processing["index"]
    assert index["title"] == INDICES["ndvi"].title
    assert index["formula"] == "(NIR - Red) / (NIR + Red)"
    # Band roles resolved against the run's asset keys.
    assert index["band_roles"] == {"red": "B04", "nir": "B08"}
    assert index["display_min"] == INDICES["ndvi"].display_min
    assert index["change_display_range"] == INDICES["ndvi"].change_display_range
    assert index["change_delta_threshold"] == INDICES["ndvi"].change_delta_threshold
    validate_provenance(doc)


def test_nbr_document_validates():
    doc = _build(index=INDICES["nbr"], change={**_change_block(), "operation": "nbr"})
    assert doc["processing"]["operation"] == "nbr"
    assert doc["processing"]["index"]["formula"] == "(NIR - SWIR2) / (NIR + SWIR2)"
    assert doc["processing"]["index"]["band_roles"] == {"nir": "B08", "swir": "B12"}
    assert doc["change"]["operation"] == "nbr"
    validate_provenance(doc)


def test_change_block_without_operation_still_valid():
    """2.1.0-era change blocks (no operation) remain valid under 2.2.0."""
    legacy = _change_block()
    del legacy["operation"]
    doc = _build(change=legacy)
    validate_provenance(doc)


def _fire_context():
    return {
        "source": "VIIRS_SNPP_SP",
        "start_date": "2024-06-01",
        "end_date": "2024-07-31",
        "bbox": [-83.15, 42.3, -83.0, 42.4],
        "windows_queried": 11,
        "windows_total": 11,
        "truncated": False,
        "detection_count": 3,
        "note": "Coordinates are NASA FIRMS VIIRS active-fire detection centroids.",
    }


def test_fire_context_validates_and_is_optional():
    """Schema 2.3.0: the FIRMS overlay block validates, and its absence does too."""
    doc = _build(fire_context=_fire_context())
    assert doc["fire_context"]["detection_count"] == 3
    assert doc["fire_context"]["source"] == "VIIRS_SNPP_SP"
    validate_provenance(doc)
    # Overlay disabled (no MAP_KEY) or fetch failed -> block omitted entirely.
    assert "fire_context" not in _build()


def test_fire_context_missing_required_field_rejected():
    bad = _fire_context()
    del bad["detection_count"]
    with pytest.raises(ValidationError):
        _build(fire_context=bad)
