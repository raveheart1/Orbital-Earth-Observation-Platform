"""Planetary Computer STAC discovery.

Searches the public Planetary Computer STAC API for Sentinel-2 L2A items and
reduces them to :class:`~earth_observation.types.SceneCandidate` objects that
carry ORIGINAL (unsigned) asset hrefs. Time-limited signed URLs are produced
only at read time (see :mod:`earth_observation.processing`) and are never
persisted as provenance.
"""

from __future__ import annotations

from typing import Any

import requests
from pystac import Item
from pystac_client import Client
from pystac_client.exceptions import APIError
from shapely.geometry import shape
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from earth_observation.errors import AssetKeysError, TransientError
from earth_observation.geometry import BBox, bbox_polygon, intersection_pct
from earth_observation.types import AssetKeys, ProcessingConfig, SceneCandidate

_RETRYABLE = (APIError, requests.ConnectionError, requests.Timeout)


def _extract_epsg(item: Item) -> int | None:
    """Read the item CRS from the STAC projection extension (proj:epsg or proj:code)."""
    props = item.properties
    epsg = props.get("proj:epsg")
    if isinstance(epsg, int):
        return epsg
    code = props.get("proj:code")
    if isinstance(code, str) and code.upper().startswith("EPSG:"):
        try:
            return int(code.split(":", 1)[1])
        except ValueError:
            return None
    return None


def candidate_from_item(item: Item, asset_keys: AssetKeys) -> SceneCandidate:
    """Convert a STAC item into a SceneCandidate, validating required assets.

    Raises :class:`AssetKeysError` when the collection does not expose the
    red / NIR / SCL assets under the expected keys, so a schema change in the
    upstream catalog fails loudly instead of producing wrong science.
    """
    required = {"red": asset_keys.red, "nir": asset_keys.nir, "scl": asset_keys.scl}
    missing = [f"{role}={key}" for role, key in required.items() if key not in item.assets]
    if missing:
        raise AssetKeysError(
            f"STAC item {item.id} is missing required assets: {', '.join(missing)}. "
            f"Available assets: {sorted(item.assets)}. The collection schema may have "
            "changed; update ProcessingConfig.asset_keys."
        )
    assets = {role: item.assets[key].href for role, key in required.items()}
    if asset_keys.visual in item.assets:
        assets["visual"] = item.assets[asset_keys.visual].href

    if item.datetime is None:
        raise AssetKeysError(f"STAC item {item.id} has no datetime")
    if item.geometry is None or item.bbox is None:
        raise AssetKeysError(f"STAC item {item.id} has no geometry")

    cloud = item.properties.get("eo:cloud_cover")
    instruments = item.properties.get("instruments")
    return SceneCandidate(
        item_id=item.id,
        collection=item.collection_id or "unknown",
        observed_at=item.datetime,
        cloud_cover_pct=float(cloud) if cloud is not None else None,
        geometry=dict(item.geometry),
        bbox=(item.bbox[0], item.bbox[1], item.bbox[2], item.bbox[3]),
        epsg=_extract_epsg(item),
        platform=item.properties.get("platform"),
        instruments=list(instruments) if instruments else None,
        processing_baseline=item.properties.get("s2:processing_baseline"),
        assets=assets,
    )


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, max=20),
    reraise=True,
)
def _run_search(
    endpoint: str,
    collection: str,
    bbox: BBox,
    start: str,
    end: str,
    max_cloud_cover_pct: float,
    max_items: int,
) -> list[Item]:
    client = Client.open(endpoint)
    search = client.search(
        collections=[collection],
        bbox=list(bbox),
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud_cover_pct}},
        max_items=max_items,
    )
    return list(search.items())


def search_scenes(
    config: ProcessingConfig,
    bbox: BBox,
    start_date: str,
    end_date: str,
    max_cloud_cover_pct: float,
) -> list[SceneCandidate]:
    """Search the STAC catalog and return chronologically sorted candidates.

    ``start_date`` / ``end_date`` are ISO dates (inclusive interval). AOI
    overlap percent is computed for each candidate so selection can filter
    scenes that barely clip the AOI.
    """
    try:
        items = _run_search(
            endpoint=config.stac_endpoint,
            collection=config.collection,
            bbox=bbox,
            start=start_date,
            end=end_date,
            max_cloud_cover_pct=max_cloud_cover_pct,
            max_items=config.max_candidate_items,
        )
    except _RETRYABLE as exc:
        raise TransientError(f"STAC search failed after retries: {exc}") from exc

    aoi = bbox_polygon(bbox)
    candidates: list[SceneCandidate] = []
    for item in items:
        candidate = candidate_from_item(item, config.asset_keys)
        candidate = candidate.model_copy(
            update={"aoi_overlap_pct": intersection_pct(aoi, shape(candidate.geometry))}
        )
        candidates.append(candidate)
    candidates.sort(key=lambda c: (c.observed_at, c.item_id))
    return candidates


def sign_href(href: str) -> str:
    """Sign a Planetary Computer asset href immediately before access.

    Isolated in one function so tests can substitute it and so no other module
    imports ``planetary_computer`` directly.
    """
    import planetary_computer

    try:
        return str(planetary_computer.sign_url(href))
    except requests.RequestException as exc:  # token endpoint failure
        raise TransientError(f"Failed to sign asset URL: {exc}") from exc


def dataset_info(config: ProcessingConfig) -> dict[str, Any]:
    """Static description of the dataset used, for the public /datasets endpoint."""
    return {
        "id": config.collection,
        "title": "Sentinel-2 Level-2A",
        "description": (
            "Atmospherically corrected surface reflectance from the Copernicus "
            "Sentinel-2 mission, accessed via the Microsoft Planetary Computer."
        ),
        "stac_endpoint": config.stac_endpoint,
        "provider": "Microsoft Planetary Computer",
        "producer": "European Space Agency (Copernicus)",
        "license": "Copernicus Sentinel data terms",
        "assets_used": config.asset_keys.model_dump(),
        "gsd_meters": 10,
    }
