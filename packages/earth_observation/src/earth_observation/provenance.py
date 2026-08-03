"""Machine-readable provenance documents and their JSON Schema.

Every completed analysis ships a provenance document containing enough
information to reproduce or audit the result: catalog endpoint and items,
original (unsigned) asset references, AOI, parameters, mask policy, software
versions, git commit, container image, CRS/transform per output, checksums,
and timing. Documents are validated against ``PROVENANCE_SCHEMA`` before
being persisted.
"""

from __future__ import annotations

from typing import Any

import jsonschema

#: 2.0.0 adds the canonical analysis grid, per-acquisition coverage accounting,
#: and every contributing granule/tile id. 1.0.0 documents predate the grid and
#: recorded a single STAC item per observation.
PROVENANCE_SCHEMA_VERSION = "2.0.0"

PROVENANCE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://raw.githubusercontent.com/raveheart1/Orbital-Earth-Observation-Platform/main/docs/schemas/provenance-2.0.0.json",
    "title": "OEOP Analysis Provenance",
    "type": "object",
    "required": [
        "schema_version",
        "analysis_id",
        "created_at",
        "data_source",
        "request",
        "canonical_grid",
        "scene_selection",
        "processing",
        "software",
        "scenes",
        "outputs",
    ],
    "properties": {
        "schema_version": {"const": PROVENANCE_SCHEMA_VERSION},
        "analysis_id": {"type": "string", "format": "uuid"},
        "created_at": {"type": "string", "format": "date-time"},
        "canonical_grid": {
            "type": "object",
            "description": (
                "The single analytical grid every observation in this analysis "
                "was reprojected onto. Identical CRS/transform/size for all "
                "usable observations by construction."
            ),
            "required": [
                "schema_version",
                "crs",
                "resolution",
                "transform",
                "width",
                "height",
                "bounds_projected",
                "bounds_geographic",
            ],
            "properties": {
                "schema_version": {"type": "string"},
                "crs": {"type": "string"},
                "epsg": {"type": "integer"},
                "resolution": {"type": "array", "items": {"type": "number"}},
                "transform": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 6,
                    "maxItems": 6,
                },
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "bounds_projected": {"type": "array", "items": {"type": "number"}},
                "bounds_geographic": {"type": "array", "items": {"type": "number"}},
                "aoi_geometry_4326": {"type": "object"},
                "signature": {"type": "string"},
            },
        },
        "data_source": {
            "type": "object",
            "required": ["stac_endpoint", "collection"],
            "properties": {
                "stac_endpoint": {"type": "string", "format": "uri"},
                "collection": {"type": "string"},
                "provider": {"type": "string"},
                "license": {"type": "string"},
            },
        },
        "request": {
            "type": "object",
            "required": ["aoi_geometry", "start_date", "end_date", "max_cloud_cover_pct"],
            "properties": {
                "aoi_geometry": {"type": "object"},
                "aoi_area_km2": {"type": "number"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "max_cloud_cover_pct": {"type": "number"},
                "scene_limit": {"type": "integer"},
            },
        },
        "scene_selection": {
            "type": "object",
            "required": [
                "algorithm",
                "algorithm_version",
                "selected_count",
                "excluded",
                "min_aoi_coverage_pct",
            ],
            "properties": {
                "algorithm": {"type": "string"},
                "algorithm_version": {"type": "string"},
                "selected_count": {"type": "integer"},
                "min_aoi_coverage_pct": {"type": "number"},
                "excluded": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["acquisition_key", "reason"],
                        "properties": {
                            "acquisition_key": {"type": "string"},
                            "primary_item_id": {"type": "string"},
                            "contributing_item_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "aoi_coverage_pct": {"type": ["number", "null"]},
                            "reason": {"type": "string"},
                        },
                    },
                },
            },
        },
        "processing": {
            "type": "object",
            "required": ["operation", "config", "mosaic_method"],
            "properties": {
                "operation": {"type": "string"},
                "config": {"type": "object"},
                "mosaic_method": {"type": "string"},
                "resampling_spectral": {"type": "string"},
                "resampling_categorical": {"type": "string"},
                "window_pad_px": {"type": "integer"},
                "masked_scl_classes": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "masked_scl_class_names": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "software": {
            "type": "object",
            "required": ["processing_version"],
            "properties": {
                "processing_version": {"type": "string"},
                "git_commit_sha": {"type": ["string", "null"]},
                "container_image": {"type": ["string", "null"]},
                "python_version": {"type": "string"},
                "dependency_lock_sha256": {"type": ["string", "null"]},
                "key_packages": {"type": "object"},
            },
        },
        "scenes": {
            "type": "array",
            "description": "One entry per ACQUISITION (may aggregate several granules)",
            "items": {
                "type": "object",
                "required": [
                    "acquisition_key",
                    "primary_item_id",
                    "contributing_item_ids",
                    "observed_at",
                    "assets",
                ],
                "properties": {
                    "acquisition_key": {"type": "string"},
                    "primary_item_id": {"type": "string"},
                    "contributing_item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "tile_ids": {"type": "array", "items": {"type": "string"}},
                    "granule_count": {"type": "integer"},
                    "observed_at": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Acquisition (sensing) time, not processing time",
                    },
                    "platform": {"type": ["string", "null"]},
                    "relative_orbit": {"type": ["string", "null"]},
                    "cloud_cover_pct": {"type": ["number", "null"]},
                    "processing_baselines": {"type": "array", "items": {"type": "string"}},
                    "band_scaling": {"type": "object"},
                    "assets": {
                        "type": "object",
                        "description": (
                            "Original unsigned asset hrefs, keyed by contributing item id then role"
                        ),
                    },
                    "coverage": {"type": ["object", "null"]},
                    "usable": {"type": "boolean"},
                    "unusable_reason": {"type": ["string", "null"]},
                    "raster": {"type": ["object", "null"]},
                    "processing_seconds": {"type": "number"},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["artifact_type", "path", "sha256", "size_bytes"],
                "properties": {
                    "artifact_type": {"type": "string"},
                    "scene_item_id": {"type": ["string", "null"]},
                    "path": {"type": "string"},
                    "content_type": {"type": "string"},
                    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "size_bytes": {"type": "integer"},
                },
            },
        },
        "timing": {
            "type": "object",
            "properties": {
                "started_at": {"type": "string", "format": "date-time"},
                "completed_at": {"type": "string", "format": "date-time"},
                "duration_seconds": {"type": "number"},
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_provenance(document: dict[str, Any]) -> None:
    """Raise ``jsonschema.ValidationError`` if the document is malformed."""
    jsonschema.validate(
        document,
        PROVENANCE_SCHEMA,
        format_checker=jsonschema.FormatChecker(),
    )


def build_provenance(
    *,
    analysis_id: str,
    created_at: str,
    config: Any,
    grid: Any,
    aoi_geometry: dict[str, Any],
    aoi_area_km2: float,
    start_date: str,
    end_date: str,
    max_cloud_cover_pct: float,
    scene_limit: int,
    selection: Any,
    results: list[Any],
    outputs: list[dict[str, Any]],
    software: dict[str, Any],
    timing: dict[str, Any],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble and validate a complete provenance document.

    ``config`` is a :class:`~earth_observation.types.ProcessingConfig`,
    ``grid`` a :class:`~earth_observation.grid.CanonicalGrid`, ``selection`` an
    :class:`~earth_observation.selection.AcquisitionSelection`, and ``results``
    a list of :class:`~earth_observation.types.SceneResult`; typed as ``Any``
    to avoid circular imports.
    """
    from earth_observation.mosaic import mosaic_metadata
    from earth_observation.types import SCLClass

    document: dict[str, Any] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "created_at": created_at,
        "data_source": {
            "stac_endpoint": config.stac_endpoint,
            "collection": config.collection,
            "provider": "Microsoft Planetary Computer",
            "license": "Copernicus Sentinel data terms",
        },
        "request": {
            "aoi_geometry": aoi_geometry,
            "aoi_area_km2": round(aoi_area_km2, 4),
            "start_date": start_date,
            "end_date": end_date,
            "max_cloud_cover_pct": max_cloud_cover_pct,
            "scene_limit": scene_limit,
        },
        "canonical_grid": grid.to_dict(),
        "scene_selection": {
            "algorithm": selection.algorithm,
            "algorithm_version": selection.algorithm_version,
            "selected_count": len(selection.selected),
            "min_aoi_coverage_pct": config.min_aoi_coverage_pct,
            "excluded": [
                {
                    "acquisition_key": e.acquisition.key,
                    "primary_item_id": e.acquisition.primary_item_id,
                    "contributing_item_ids": e.acquisition.item_ids,
                    "aoi_coverage_pct": round(e.acquisition.aoi_coverage_pct, 4),
                    "reason": e.reason,
                }
                for e in selection.excluded
            ],
        },
        "processing": {
            "operation": "ndvi",
            "config": config.model_dump(),
            "masked_scl_classes": list(config.masked_scl_classes),
            "masked_scl_class_names": [SCLClass(c).name for c in config.masked_scl_classes],
            **mosaic_metadata(),
        },
        "software": software,
        "scenes": [
            {
                "acquisition_key": r.acquisition.key,
                "primary_item_id": r.acquisition.primary_item_id,
                "contributing_item_ids": r.acquisition.contributing_item_ids,
                "tile_ids": r.acquisition.tile_ids,
                "granule_count": len(r.acquisition.contributing_item_ids),
                "observed_at": r.acquisition.observed_at.isoformat(),
                "platform": r.acquisition.platform,
                "relative_orbit": r.acquisition.relative_orbit,
                "cloud_cover_pct": r.acquisition.cloud_cover_pct,
                "processing_baselines": r.acquisition.processing_baselines,
                "band_scaling": r.scaling.model_dump() if r.scaling else {},
                "assets": r.acquisition.assets,
                "coverage": r.coverage.model_dump() if r.coverage else None,
                "usable": r.usable,
                "unusable_reason": r.unusable_reason,
                "raster": r.raster.model_dump() if r.raster else None,
                "processing_seconds": r.processing_seconds,
                "warnings": r.warnings,
            }
            for r in results
        ],
        "outputs": outputs,
        "timing": timing,
        "warnings": warnings or [],
    }
    validate_provenance(document)
    return document
