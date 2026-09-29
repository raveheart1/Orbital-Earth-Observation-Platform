"""Deterministic cache keys for per-acquisition measurements.

Temporal context multiplies work: a baseline needs dozens of historical
acquisitions measured on the analysis's canonical grid. Those measurements
depend only on inputs that can be enumerated exactly, so they are cached
under a key derived from ALL of them. Two analyses over the same curated
region (identical grid) with the same index, mask policy, and land-cover map
share measurements; any change to an input changes the key, so a stale
entry can never be returned for a different computation.

The cache stores measurements only (statistics, coverage, class statistics),
never artifacts, and is safe to empty at any time: a miss recomputes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from earth_observation.acquisition import Acquisition
from earth_observation.grid import CanonicalGrid
from earth_observation.indices import IndexDefinition
from earth_observation.types import ProcessingConfig

#: Bump when the cached measurement's shape or meaning changes.
MEASUREMENT_CACHE_VERSION = "1"


def measurement_cache_identity(
    *,
    grid: CanonicalGrid,
    acquisition: Acquisition,
    index: IndexDefinition,
    config: ProcessingConfig,
    processing_version: str,
    land_cover: dict[str, Any] | None,
) -> dict[str, Any]:
    """Every input that determines an acquisition's measurement.

    ``land_cover`` is :meth:`LandCoverLayer.cache_identity` (or None when no
    land-cover stratification was applied).
    """
    return {
        "cache_version": MEASUREMENT_CACHE_VERSION,
        "processing_version": processing_version,
        "grid_signature": grid.signature(),
        "aoi_geometry_4326": grid.aoi_geometry_4326,
        "collection": acquisition.collection,
        "acquisition_key": acquisition.key,
        "contributing_item_ids": sorted(acquisition.item_ids),
        "operation": index.operation,
        "formula": index.formula,
        "band_assets": {
            role: getattr(config.asset_keys, role) for role in index.required_band_roles
        },
        "scl_asset": config.asset_keys.scl,
        "masked_scl_classes": sorted(int(c) for c in config.masked_scl_classes),
        "min_aoi_coverage_pct": config.min_aoi_coverage_pct,
        "min_valid_pixel_pct": config.min_valid_pixel_pct,
        "land_cover": land_cover,
        "land_cover_thresholds": config.land_cover.model_dump() if land_cover else None,
    }


def measurement_cache_key(identity: dict[str, Any]) -> str:
    """SHA-256 hex digest of the canonical JSON encoding of ``identity``."""
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def land_cover_cache_key(
    *, dataset_id: str, item_ids: list[str], grid: CanonicalGrid, resampling: str
) -> str:
    """Key for an aligned land-cover raster cached in blob storage."""
    return measurement_cache_key(
        {
            "kind": "land_cover_raster",
            "cache_version": MEASUREMENT_CACHE_VERSION,
            "dataset_id": dataset_id,
            "item_ids": sorted(item_ids),
            "grid_signature": grid.signature(),
            "aoi_geometry_4326": grid.aoi_geometry_4326,
            "resampling": resampling,
        }
    )
