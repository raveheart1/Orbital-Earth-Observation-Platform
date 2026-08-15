"""Thin client for the NASA FIRMS Area API (active-fire detections).

FIRMS serves VIIRS/MODIS active-fire detections as CSV over plain HTTP GET:

    /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{DATE}

returning detections for ``DATE .. DATE + DAY_RANGE - 1`` (DAY_RANGE is
documented as 1..5; see https://firms.modaps.eosdis.nasa.gov/api/area/). An
analysis span can be a year or more, so :func:`fetch_fire_detections` chunks
the span into consecutive windows and merges the results, bounding the call
count (MAP_KEYs are limited to 5000 transactions per 10 minutes, and
multi-day requests count as several).

The default source is ``VIIRS_SNPP_SP`` (standard processing): the SP archive
reaches back to 2012, while NRT products only cover recent days — analysis
spans may reach years back (e.g. the 2021 Evia fire).

Stdlib ``urllib`` is used deliberately: the payload is a single GET per
window and ``oeop_core`` has no HTTP dependency of its own. Everything here
is best-effort context for an analysis — callers catch :class:`FirmsError`
and degrade to a warning; nothing in this module may fail an analysis run.
"""

from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

#: Default product: VIIRS Suomi-NPP standard processing (full archive).
DEFAULT_SOURCE = "VIIRS_SNPP_SP"

#: Documented maximum DAY_RANGE per Area API call.
DAY_RANGE_PER_REQUEST = 5

#: CSV header of a well-formed response (first column). Anything else in the
#: first line means FIRMS returned an error message instead of data.
_CSV_FIRST_COLUMN = "latitude"


class FirmsError(Exception):
    """Any FIRMS fetch/parsing failure. Always caught by the worker."""


class FirmsAuthError(FirmsError):
    """The MAP_KEY was rejected (FIRMS answers with an 'Invalid MAP_KEY' text)."""


class FirmsResponseError(FirmsError):
    """FIRMS returned a non-CSV body (error text, over-limit notice, HTML)."""


@dataclass
class FirmsFetchResult:
    """Merged detections plus an honest record of how they were fetched."""

    geojson: dict[str, Any]
    detection_count: int
    source: str
    start_date: str
    end_date: str
    windows_queried: int
    windows_total: int
    #: True when ``max_windows`` bound the query: the returned points cover
    #: only the first ``windows_queried`` windows counting from start_date.
    truncated: bool


def date_windows(
    start: date, end: date, day_range: int = DAY_RANGE_PER_REQUEST
) -> list[tuple[date, int]]:
    """Consecutive (window_start, days) pairs covering [start, end] inclusive."""
    if end < start:
        raise ValueError(f"end date {end} is before start date {start}")
    windows: list[tuple[date, int]] = []
    cursor = start
    while cursor <= end:
        days = min(day_range, (end - cursor).days + 1)
        windows.append((cursor, days))
        cursor += timedelta(days=days)
    return windows


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def detections_to_geojson(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Map FIRMS CSV rows to a GeoJSON FeatureCollection (EPSG:4326 points).

    VIIRS products name the brightness column ``bright_ti4``, MODIS names it
    ``brightness``; both map to the ``brightness`` property.
    """
    features: list[dict[str, Any]] = []
    for row in rows:
        lat = _float_or_none(row.get("latitude"))
        lon = _float_or_none(row.get("longitude"))
        if lat is None or lon is None:
            continue  # a detection without coordinates is unusable as a point
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "acq_date": row.get("acq_date"),
                    "acq_time": row.get("acq_time"),
                    "brightness": _float_or_none(row.get("bright_ti4") or row.get("brightness")),
                    "confidence": row.get("confidence"),
                    "frp": _float_or_none(row.get("frp")),
                    "daynight": row.get("daynight"),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _classify_body(text: str) -> None:
    """Raise on FIRMS error bodies; return None for a well-formed CSV."""
    first_line = text.lstrip().splitlines()[0] if text.strip() else ""
    if first_line.startswith(_CSV_FIRST_COLUMN):
        return
    if "Invalid MAP_KEY" in text:
        raise FirmsAuthError("FIRMS rejected the MAP_KEY (Invalid MAP_KEY)")
    raise FirmsResponseError(
        "FIRMS returned a non-CSV response (error notice or transaction "
        f"over-limit message): {first_line[:200]!r}"
    )


def parse_csv(text: str) -> list[dict[str, str]]:
    """Parse a FIRMS CSV body. A header-only body yields an empty list."""
    _classify_body(text)
    return list(csv.DictReader(io.StringIO(text)))


def _get_text(url: str, timeout_seconds: float) -> str:
    """One HTTP GET, with every failure mode mapped onto FirmsError."""
    request = urllib.request.Request(url, headers={"User-Agent": "oeop-worker"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload: bytes = response.read()
            return payload.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403) or "Invalid MAP_KEY" in body:
            raise FirmsAuthError(f"FIRMS rejected the MAP_KEY (HTTP {exc.code})") from exc
        raise FirmsError(f"FIRMS request failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise FirmsError(f"FIRMS request failed: {exc.reason}") from exc


def fetch_fire_detections(
    *,
    map_key: str,
    source: str = DEFAULT_SOURCE,
    bbox: tuple[float, float, float, float],
    start: date,
    end: date,
    max_windows: int,
    timeout_seconds: float = 30.0,
    get_text: Callable[[str, float], str] = _get_text,
) -> FirmsFetchResult:
    """Fetch detections for ``bbox`` (west, south, east, north) over [start, end].

    The span is queried in chronological windows of at most
    ``DAY_RANGE_PER_REQUEST`` days, starting at ``start``. When the span needs
    more than ``max_windows`` calls the trailing windows are skipped and the
    result is marked ``truncated`` — the caller records this so provenance
    stays honest about partial coverage.

    ``get_text`` is injectable so tests exercise the real parsing and
    chunking logic without the network.
    """
    west, south, east, north = bbox
    windows = date_windows(start, end)
    windows_total = len(windows)
    truncated = windows_total > max_windows
    queried = windows[:max_windows]

    rows: list[dict[str, str]] = []
    for window_start, days in queried:
        url = (
            f"{BASE_URL}/{map_key}/{source}/"
            f"{west},{south},{east},{north}/{days}/{window_start.isoformat()}"
        )
        rows.extend(parse_csv(get_text(url, timeout_seconds)))

    geojson = detections_to_geojson(rows)
    return FirmsFetchResult(
        geojson=geojson,
        detection_count=len(geojson["features"]),
        source=source,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        windows_queried=len(queried),
        windows_total=windows_total,
        truncated=truncated,
    )
