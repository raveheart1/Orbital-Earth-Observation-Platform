"""FIRMS Area API client tests: parsing, error taxonomy, window chunking.

All network access is substituted via the ``get_text`` injection point; the
CSV fixtures mirror real VIIRS_SNPP_SP response shapes.
"""

from __future__ import annotations

import urllib.error
from datetime import date

import pytest

from oeop_core.firms import (
    DAY_RANGE_PER_REQUEST,
    FirmsAuthError,
    FirmsError,
    FirmsResponseError,
    date_windows,
    detections_to_geojson,
    fetch_fire_detections,
    parse_csv,
)

HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight,type"
)
ROW_1 = "38.963,23.712,331.4,0.42,0.36,2021-08-08,1235,N,VIIRS,n,2.0,291.2,45.7,D,0"
ROW_2 = "39.102,23.855,348.9,0.51,0.40,2021-08-08,1235,N,VIIRS,h,2.0,298.6,110.3,D,0"

BBOX = (22.5, 38.0, 24.5, 39.5)
START = date(2021, 8, 1)
END = date(2021, 8, 10)


def _stub(body: str):
    return lambda url, timeout: body


class TestParsing:
    def test_real_rows_map_to_features(self):
        rows = parse_csv(f"{HEADER}\n{ROW_1}\n{ROW_2}\n")
        geojson = detections_to_geojson(rows)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 2
        feature = geojson["features"][0]
        assert feature["geometry"] == {"type": "Point", "coordinates": [23.712, 38.963]}
        props = feature["properties"]
        assert props["acq_date"] == "2021-08-08"
        assert props["acq_time"] == "1235"
        assert props["brightness"] == pytest.approx(331.4)  # VIIRS bright_ti4
        assert props["confidence"] == "n"
        assert props["frp"] == pytest.approx(45.7)
        assert props["daynight"] == "D"

    def test_header_only_is_empty_not_an_error(self):
        assert parse_csv(HEADER + "\n") == []
        assert detections_to_geojson([])["features"] == []

    def test_modis_brightness_column_maps(self):
        header = HEADER.replace("bright_ti4", "brightness")
        row = ROW_1.split(",")
        rows = parse_csv(f"{header}\n{','.join(row)}\n")
        feature = detections_to_geojson(rows)["features"][0]
        assert feature["properties"]["brightness"] == pytest.approx(331.4)

    def test_row_without_coordinates_is_skipped(self):
        bad = ROW_1.replace("38.963", "", 1)
        rows = parse_csv(f"{HEADER}\n{ROW_1}\n{bad}\n")
        assert len(detections_to_geojson(rows)["features"]) == 1

    def test_invalid_map_key_raises_auth_error(self):
        with pytest.raises(FirmsAuthError, match="MAP_KEY"):
            parse_csv(
                "Invalid MAP_KEY. Get one at https://firms.modaps.eosdis.nasa.gov/api/map_key/"
            )

    def test_non_csv_error_text_raises_response_error(self):
        with pytest.raises(FirmsResponseError, match="non-CSV"):
            parse_csv("You have exceeded your transaction limit for this interval")

    def test_empty_body_raises_response_error(self):
        with pytest.raises(FirmsResponseError):
            parse_csv("")


class TestWindows:
    def test_short_span_is_one_window(self):
        assert date_windows(date(2024, 1, 1), date(2024, 1, 5)) == [
            (date(2024, 1, 1), DAY_RANGE_PER_REQUEST)
        ]

    def test_span_splits_into_consecutive_windows(self):
        windows = date_windows(date(2024, 1, 1), date(2024, 1, 6))
        assert windows == [(date(2024, 1, 1), 5), (date(2024, 1, 6), 1)]

    def test_year_span_math(self):
        windows = date_windows(date(2024, 1, 1), date(2024, 12, 31))
        assert len(windows) == 74  # ceil(366 / 5)
        assert windows[-1] == (date(2024, 12, 31), 1)  # 366 = 73*5 + 1
        # Windows are consecutive and cover the span exactly.
        covered = sum(days for _, days in windows)
        assert covered == 366

    def test_end_before_start_rejected(self):
        with pytest.raises(ValueError, match="before start"):
            date_windows(date(2024, 2, 1), date(2024, 1, 1))


class TestFetch:
    def test_merges_windows_and_reports_counts(self):
        bodies = iter([f"{HEADER}\n{ROW_1}\n", f"{HEADER}\n{ROW_2}\n"])
        calls: list[str] = []

        def stub(url: str, timeout: float) -> str:
            calls.append(url)
            return next(bodies)

        result = fetch_fire_detections(
            map_key="TESTKEY",
            bbox=BBOX,
            start=START,
            end=END,  # 10 days -> 2 windows of 5
            max_windows=75,
            get_text=stub,
        )
        assert result.detection_count == 2
        assert result.windows_queried == 2
        assert result.windows_total == 2
        assert result.truncated is False
        assert result.source == "VIIRS_SNPP_SP"
        assert len(calls) == 2
        assert "/TESTKEY/VIIRS_SNPP_SP/22.5,38.0,24.5,39.5/5/2021-08-01" in calls[0]
        assert calls[1].endswith("/5/2021-08-06")

    def test_cap_binds_and_marks_truncated(self):
        result = fetch_fire_detections(
            map_key="TESTKEY",
            bbox=BBOX,
            start=START,
            end=date(2021, 8, 20),  # 20 days -> 4 windows
            max_windows=2,
            get_text=_stub(f"{HEADER}\n{ROW_1}\n"),
        )
        assert result.windows_queried == 2
        assert result.windows_total == 4
        assert result.truncated is True
        assert result.detection_count == 2  # one row per queried window

    def test_empty_windows_merge_to_empty(self):
        result = fetch_fire_detections(
            map_key="TESTKEY",
            bbox=BBOX,
            start=START,
            end=END,
            max_windows=75,
            get_text=_stub(HEADER + "\n"),
        )
        assert result.detection_count == 0
        assert result.geojson["features"] == []

    def test_invalid_key_propagates_as_auth_error(self):
        with pytest.raises(FirmsAuthError):
            fetch_fire_detections(
                map_key="BAD",
                bbox=BBOX,
                start=START,
                end=END,
                max_windows=75,
                get_text=_stub("Invalid MAP_KEY"),
            )


class TestHttpMapping:
    def test_401_maps_to_auth_error(self, monkeypatch):
        import io

        from oeop_core import firms

        def raise_401(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"Invalid MAP_KEY")
            )

        monkeypatch.setattr(urllib.request, "urlopen", raise_401)
        with pytest.raises(FirmsAuthError):
            firms._get_text("https://example.test/x", 5.0)

    def test_connection_failure_maps_to_firms_error(self, monkeypatch):
        from oeop_core import firms

        def raise_url_error(request, timeout):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", raise_url_error)
        with pytest.raises(FirmsError, match="connection refused"):
            firms._get_text("https://example.test/x", 5.0)
