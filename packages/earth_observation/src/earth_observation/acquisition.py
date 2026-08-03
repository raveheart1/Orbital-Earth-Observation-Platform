"""Acquisition grouping.

A single Sentinel-2 acquisition is distributed as one STAC item per 110 km
military-grid tile. An AOI that straddles a tile boundary therefore matches
SEVERAL items that represent the SAME observation instant — for example
Detroit Urban Core matches both T17TLG (100 % of the AOI) and T17TLH (56 %).

Treating those items as independent scenes is what produced observations with
different footprints. Here they are grouped into one :class:`Acquisition`
whose granules are later mosaicked onto the canonical grid.

Grouping key
------------
Items belong to the same acquisition when they share:

* observation time rounded to the nearest minute (granules of one acquisition
  share a datetime to sub-second precision; rounding absorbs metadata jitter),
* platform (``sentinel-2a`` / ``-2b`` / ``-2c``) — different satellites can
  pass within minutes of each other,
* relative orbit (``R040``) — parsed from the item id, distinguishing adjacent
  swaths acquired the same day,
* processing level (the STAC collection).

Deliberately NOT part of the key: the tile id (the thing that differs) and the
processing timestamp (granules of one acquisition are often processed at
different times — that is exactly why it must be excluded).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from shapely.geometry import shape
from shapely.ops import unary_union

from earth_observation.geometry import intersection_pct
from earth_observation.types import SceneCandidate

#: Sentinel-2 product id: S2A_MSIL2A_<datetime>_<orbit>_<tile>_<processing>
_S2_ID = re.compile(
    r"^(?P<platform>S2[A-D])_(?P<level>MSIL[12][ABC])_(?P<sensing>\d{8}T\d{6})_"
    r"(?P<orbit>R\d{3})_(?P<tile>T[0-9]{2}[A-Z]{3})_(?P<processing>\d{8}T\d{6})$"
)


def parse_tile_id(item_id: str) -> str | None:
    """Sentinel-2 MGRS tile identifier (e.g. ``T17TLG``) from a product id."""
    match = _S2_ID.match(item_id)
    return match.group("tile") if match else None


def parse_relative_orbit(item_id: str) -> str | None:
    match = _S2_ID.match(item_id)
    return match.group("orbit") if match else None


def acquisition_key(candidate: SceneCandidate) -> str:
    """Deterministic key identifying the acquisition a granule belongs to."""
    observed = candidate.observed_at.replace(second=0, microsecond=0)
    orbit = parse_relative_orbit(candidate.item_id) or "Rxxx"
    platform = (candidate.platform or "unknown").lower()
    return f"{candidate.collection}|{platform}|{orbit}|{observed.isoformat()}"


@dataclass
class Acquisition:
    """One observation instant, backed by one or more granules."""

    key: str
    observed_at: datetime
    platform: str | None
    relative_orbit: str | None
    collection: str
    granules: list[SceneCandidate]
    #: Percent of the AOI covered by the UNION of granule footprints.
    aoi_coverage_pct: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def item_ids(self) -> list[str]:
        return [g.item_id for g in self.granules]

    @property
    def tile_ids(self) -> list[str]:
        tiles = {parse_tile_id(g.item_id) for g in self.granules}
        return sorted(t for t in tiles if t)

    @property
    def granule_count(self) -> int:
        return len(self.granules)

    @property
    def primary_item_id(self) -> str:
        """Stable representative id (the granule covering most of the AOI).

        Ties break on item id so the choice is reproducible.
        """
        return max(
            self.granules,
            key=lambda g: (g.aoi_overlap_pct or 0.0, g.item_id),
        ).item_id

    @property
    def cloud_cover_pct(self) -> float | None:
        """Coverage-weighted mean cloud cover across contributing granules.

        Weighting by AOI overlap keeps a mostly-irrelevant neighbouring granule
        from dominating the figure quoted for the acquisition.
        """
        weighted: list[tuple[float, float]] = [
            (g.cloud_cover_pct, max(g.aoi_overlap_pct or 0.0, 1e-6))
            for g in self.granules
            if g.cloud_cover_pct is not None
        ]
        if not weighted:
            return None
        total = sum(w for _, w in weighted)
        return sum(value * w for value, w in weighted) / total

    @property
    def processing_baselines(self) -> list[str]:
        return sorted({g.processing_baseline for g in self.granules if g.processing_baseline})


def group_acquisitions(
    candidates: list[SceneCandidate], aoi_geojson: dict[str, Any]
) -> list[Acquisition]:
    """Group granules into acquisitions and compute union AOI coverage.

    Returned acquisitions are sorted chronologically; granules within each are
    sorted by item id so downstream mosaicking is deterministic.
    """
    aoi = shape(aoi_geojson)
    grouped: dict[str, list[SceneCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(acquisition_key(candidate), []).append(candidate)

    acquisitions: list[Acquisition] = []
    for key, granules in grouped.items():
        granules.sort(key=lambda g: g.item_id)
        footprint = unary_union([shape(g.geometry) for g in granules])
        first = granules[0]
        warnings: list[str] = []
        baselines = {g.processing_baseline for g in granules if g.processing_baseline}
        if len(baselines) > 1:
            warnings.append(
                "Contributing granules use different processing baselines "
                f"({sorted(baselines)}); reflectance offsets are resolved per granule"
            )
        acquisitions.append(
            Acquisition(
                key=key,
                observed_at=min(g.observed_at for g in granules),
                platform=first.platform,
                relative_orbit=parse_relative_orbit(first.item_id),
                collection=first.collection,
                granules=granules,
                aoi_coverage_pct=intersection_pct(aoi, footprint),
                warnings=warnings,
            )
        )

    acquisitions.sort(key=lambda a: (a.observed_at, a.key))
    return acquisitions


def max_time_spread(acquisition: Acquisition) -> timedelta:
    """Largest time difference between contributing granules (sanity check)."""
    times = [g.observed_at for g in acquisition.granules]
    return max(times) - min(times)
