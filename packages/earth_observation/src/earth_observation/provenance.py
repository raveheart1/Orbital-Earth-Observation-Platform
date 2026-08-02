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

PROVENANCE_SCHEMA_VERSION = "1.0.0"

PROVENANCE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://raw.githubusercontent.com/raveheart1/Orbital-Earth-Observation-Platform/main/docs/schemas/provenance-1.0.0.json",
    "title": "OEOP Analysis Provenance",
    "type": "object",
    "required": [
        "schema_version",
        "analysis_id",
        "created_at",
        "data_source",
        "request",
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
            "required": ["algorithm", "algorithm_version", "selected_count", "excluded"],
            "properties": {
                "algorithm": {"type": "string"},
                "algorithm_version": {"type": "string"},
                "selected_count": {"type": "integer"},
                "excluded": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["item_id", "reason"],
                        "properties": {
                            "item_id": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                    },
                },
            },
        },
        "processing": {
            "type": "object",
            "required": ["operation", "config"],
            "properties": {
                "operation": {"type": "string"},
                "config": {"type": "object"},
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
            "items": {
                "type": "object",
                "required": ["item_id", "observed_at", "assets"],
                "properties": {
                    "item_id": {"type": "string"},
                    "observed_at": {"type": "string", "format": "date-time"},
                    "cloud_cover_pct": {"type": ["number", "null"]},
                    "processing_baseline": {"type": ["string", "null"]},
                    "band_scaling": {"type": "object"},
                    "assets": {
                        "type": "object",
                        "description": "Original unsigned asset hrefs by role",
                        "additionalProperties": {"type": "string"},
                    },
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
    ``selection`` a :class:`~earth_observation.types.SceneSelection`, and
    ``results`` a list of :class:`~earth_observation.types.SceneResult`;
    typed as ``Any`` to avoid a circular import with :mod:`.types`.
    """
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
        "scene_selection": {
            "algorithm": selection.algorithm,
            "algorithm_version": selection.algorithm_version,
            "selected_count": len(selection.selected),
            "excluded": [
                {"item_id": e.candidate.item_id, "reason": e.reason} for e in selection.excluded
            ],
        },
        "processing": {
            "operation": "ndvi",
            "config": config.model_dump(),
            "masked_scl_classes": list(config.masked_scl_classes),
            "masked_scl_class_names": [SCLClass(c).name for c in config.masked_scl_classes],
        },
        "software": software,
        "scenes": [
            {
                "item_id": r.candidate.item_id,
                "observed_at": r.candidate.observed_at.isoformat(),
                "cloud_cover_pct": r.candidate.cloud_cover_pct,
                "processing_baseline": r.candidate.processing_baseline,
                "band_scaling": r.scaling.model_dump() if r.scaling else {},
                "assets": r.candidate.assets,
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
