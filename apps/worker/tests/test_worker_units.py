"""Worker unit tests that require no external services."""

from __future__ import annotations

import functools
import hashlib
import json
import time
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from rasterio.transform import from_origin

from earth_observation.errors import DataError, UserInputError
from earth_observation.indices import INDICES
from earth_observation.processing import process_acquisition
from earth_observation.provenance import PROVENANCE_SCHEMA_VERSION
from earth_observation.stac import SceneSearchResult
from earth_observation.testing import (
    NODATA_DN,
    ORIGIN_X,
    ORIGIN_Y,
    RES,
    SIZE,
    utm_box_to_wgs84_geojson,
    write_raster,
)
from earth_observation.testing import (
    make_file_candidate as make_candidate,
)
from earth_observation.types import AcquisitionSummary, SceneCandidate, SceneResult
from oeop_core.db.models import Artifact, ArtifactType, Observation
from oeop_core.firms import FirmsError
from oeop_core.settings import Settings
from oeop_core.telemetry import WorkerMetrics
from oeop_worker import runner
from oeop_worker.runner import _comparison_endpoints, _software_metadata, _StorageBudget


def test_storage_budget_enforced():
    budget = _StorageBudget(limit_mb=1, analysis_id="x")
    budget.charge(512 * 1024)
    budget.charge(400 * 1024)
    with pytest.raises(DataError, match="storage limit"):
        budget.charge(512 * 1024)


def test_software_metadata_complete():
    settings = Settings(_env_file=None, git_commit_sha="abc123")
    meta = _software_metadata(settings)
    assert meta["processing_version"]
    assert meta["git_commit_sha"] == "abc123"
    assert meta["python_version"].startswith("3.")
    assert "rasterio" in meta["key_packages"]
    assert meta["key_packages"]["rasterio"] != "unknown"


def _result(item_id: str, observed_at: datetime, usable: bool) -> SceneResult:
    return SceneResult(
        acquisition=AcquisitionSummary(
            key=item_id,
            primary_item_id=item_id,
            observed_at=observed_at,
            collection="sentinel-2-l2a",
            platform="sentinel-2a",
            relative_orbit=None,
            cloud_cover_pct=5.0,
            contributing_item_ids=[item_id],
            tile_ids=["T17TLH"],
            processing_baselines=["05.00"],
        ),
        usable=usable,
    )


def test_comparison_endpoints_mirror_web_semantics():
    """Earliest and latest USABLE observations, like selectComparisonPoints."""
    a = _result("a", datetime(2024, 5, 1, tzinfo=UTC), True)
    b = _result("b", datetime(2024, 6, 1, tzinfo=UTC), True)
    c = _result("c", datetime(2024, 7, 1, tzinfo=UTC), True)
    unusable_early = _result("x", datetime(2024, 4, 1, tzinfo=UTC), False)
    unusable_late = _result("y", datetime(2024, 8, 1, tzinfo=UTC), False)
    endpoints = _comparison_endpoints([c, unusable_late, a, b, unusable_early])
    assert endpoints is not None
    earlier, later = endpoints
    assert (earlier.item_id, later.item_id) == ("a", "c")


def test_comparison_endpoints_need_two_usable():
    a = _result("a", datetime(2024, 5, 1, tzinfo=UTC), True)
    unusable = _result("x", datetime(2024, 6, 1, tzinfo=UTC), False)
    assert _comparison_endpoints([a, unusable]) is None
    assert _comparison_endpoints([]) is None


def test_provenance_records_search_metadata_and_analysis_warnings():
    """The truncation warning must reach provenance, not just the log.

    `_run_pipeline` computes `analysis_warnings` (including "the catalog search
    hit its per-window cap, so more acquisitions may exist") and a
    `SceneSearchResult`, but both were once dropped on the floor because the
    `build_provenance` call omitted the keyword arguments. The provenance
    document then advertised an empty `warnings` array while the worker knew
    the result was incomplete, which is the opposite of an audit trail.
    """
    import ast
    import inspect

    from oeop_worker import runner

    tree = ast.parse(inspect.getsource(runner))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_provenance"
    ]
    assert calls, "build_provenance is no longer called by the runner"
    for call in calls:
        passed = {kw.arg for kw in call.keywords}
        assert "warnings" in passed, "analysis warnings are not persisted to provenance"
        assert "search" in passed, "catalog search metadata is not persisted to provenance"


def test_provenance_records_change_block():
    """The change map's source pair and parameters must reach provenance."""
    import ast
    import inspect

    from oeop_worker import runner

    tree = ast.parse(inspect.getsource(runner))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_provenance"
    ]
    assert calls, "build_provenance is no longer called by the runner"
    for call in calls:
        passed = {kw.arg for kw in call.keywords}
        assert "change" in passed, "the change block is not persisted to provenance"


# ---------------------------------------------------------------------------
# End-to-end pipeline tests over synthetic granule GeoTIFFs
#
# These run _run_pipeline for real — windowed reads, mosaicking, index
# computation, change map, artifact upload bookkeeping, provenance — with the
# STAC search, URL signer, database session, and blob store substituted.
# ---------------------------------------------------------------------------

AOI_GEOJSON = utm_box_to_wgs84_geojson(
    ORIGIN_X + 10 * RES,
    ORIGIN_Y - 30 * RES,
    ORIGIN_X + 30 * RES,
    ORIGIN_Y - 10 * RES,
)

JUNE = datetime(2024, 6, 15, 16, 30, tzinfo=UTC)
JULY = datetime(2024, 7, 15, 16, 30, tzinfo=UTC)
JUNE_ID = "S2A_MSIL2A_20240615T163000_R040_T17TLH_20240615T200000"
JULY_ID = "S2A_MSIL2A_20240715T163000_R040_T17TLH_20240715T200000"


class _FakeSession:
    """Records added rows; statements are no-ops (no database needed)."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def execute(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(first=lambda: None)

    async def commit(self) -> None:
        pass


class _FakeBlob:
    """In-memory blob store capturing uploads by blob path."""

    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}
        self._settings = SimpleNamespace(artifacts_container="test-artifacts")

    def delete_prefix(self, prefix: str) -> int:
        return 0

    def upload_file(self, local_path: Path, blob_path: str, content_type: str) -> SimpleNamespace:
        data = Path(local_path).read_bytes()
        self.uploads[blob_path] = data
        return SimpleNamespace(size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def _write_scene(
    scene_dir: Path,
    *,
    item_id: str,
    observed_at: datetime,
    bands: dict[str, tuple[int, int]],
) -> SceneCandidate:
    """One synthetic granule; ``bands`` maps role -> (DN value, pixel size m)."""
    scene_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[str, str] = {}
    for role, (dn, pixel_m) in bands.items():
        side = SIZE * RES // pixel_m
        data = np.full((int(side), int(side)), dn, dtype=np.uint16)
        write_raster(
            scene_dir / f"{role}.tif",
            data,
            transform=from_origin(ORIGIN_X, ORIGIN_Y, pixel_m, pixel_m),
            nodata=NODATA_DN,
        )
        assets[role] = str(scene_dir / f"{role}.tif")
    scl = np.full((SIZE // 2, SIZE // 2), 4, dtype=np.uint8)  # 20 m: vegetation
    write_raster(
        scene_dir / "scl.tif",
        scl,
        transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
        nodata=0,
    )
    assets["scl"] = str(scene_dir / "scl.tif")
    return make_candidate(scene_dir, item_id=item_id, with_visual=False).model_copy(
        update={"observed_at": observed_at, "assets": assets}
    )


def _nbr_candidates(root: Path) -> list[SceneCandidate]:
    """June: healthy vegetation (NBR 0.6); July: burned (NBR -0.5)."""
    return [
        _write_scene(
            root / "june",
            item_id=JUNE_ID,
            observed_at=JUNE,
            bands={"nir": (5000, 10), "swir": (2000, 20)},
        ),
        _write_scene(
            root / "july",
            item_id=JULY_ID,
            observed_at=JULY,
            bands={"nir": (2000, 10), "swir": (4000, 20)},
        ),
    ]


def _ndvi_candidates(root: Path) -> list[SceneCandidate]:
    """Two dates of identical NDVI 0.5 (red DN 2000, NIR DN 4000)."""
    return [
        _write_scene(
            root / name,
            item_id=item_id,
            observed_at=observed,
            bands={"red": (2000, 10), "nir": (4000, 10)},
        )
        for name, item_id, observed in (("june", JUNE_ID, JUNE), ("july", JULY_ID, JULY))
    ]


def _fake_analysis(operation: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        operation=operation,
        processing_config={"preview_max_dim": 256},
        geometry=None,
        region_id=None,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 7, 31),
        max_cloud_cover_pct=20.0,
        scene_limit=10,
        selection_strategy="temporal",
        seasonal_target_month=None,
        area_km2=0.04,
        started_at=None,
    )


async def _run_fake_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    candidates: list[SceneCandidate],
    operation: str,
    settings: Settings | None = None,
) -> tuple[Any, _FakeSession, _FakeBlob]:
    analysis = _fake_analysis(operation)
    session = _FakeSession()
    blob = _FakeBlob()

    def fake_search(*args: Any, **kwargs: Any) -> SceneSearchResult:
        return SceneSearchResult(
            candidates=candidates,
            windows=[("2024-06-01", "2024-07-31")],
            max_items_per_window=150,
        )

    async def fake_aoi(session: Any, analysis: Any) -> dict[str, Any]:
        return AOI_GEOJSON

    monkeypatch.setattr(runner, "search_scenes", fake_search)
    monkeypatch.setattr(runner, "_aoi_geojson", fake_aoi)
    monkeypatch.setattr(
        runner, "process_acquisition", functools.partial(process_acquisition, sign=str)
    )

    outcome = await runner._run_pipeline(
        session,  # type: ignore[arg-type]
        analysis,
        settings or Settings(_env_file=None),
        blob,  # type: ignore[arg-type]
        WorkerMetrics(),
        time.monotonic() + 3600,
    )
    return outcome, session, blob


def _added(session: _FakeSession, cls: type) -> list[Any]:
    return [row for row in session.added if isinstance(row, cls)]


async def test_nbr_analysis_end_to_end(monkeypatch, tmp_path):
    outcome, session, blob = await _run_fake_pipeline(
        monkeypatch, tmp_path, _nbr_candidates(tmp_path / "scenes"), "nbr"
    )
    assert outcome.status == "succeeded", outcome.detail

    artifact_types = {a.artifact_type for a in _added(session, Artifact)}
    assert {
        ArtifactType.NBR_COG,
        ArtifactType.NBR_PREVIEW,
        ArtifactType.NBR_CHANGE_COG,
        ArtifactType.NBR_CHANGE_PREVIEW,
    } <= artifact_types
    assert ArtifactType.NDVI_COG not in artifact_types
    assert ArtifactType.NDVI_CHANGE_COG not in artifact_types

    prefix = f"analyses/{_fake_id(session)}"
    for name in ("nbr.tif", "nbr_preview.png"):
        assert f"{prefix}/scenes/{JUNE_ID}/{name}" in blob.uploads
        assert f"{prefix}/scenes/{JULY_ID}/{name}" in blob.uploads
    assert f"{prefix}/nbr_change.tif" in blob.uploads
    assert f"{prefix}/nbr_change_preview.png" in blob.uploads

    observations = _added(session, Observation)
    assert len(observations) == 2
    assert all(o.processing_params["operation"] == "nbr" for o in observations)

    summary = json.loads(blob.uploads[f"{prefix}/summary.json"])
    change = summary["change"]
    assert change["computed"] is True
    assert change["operation"] == "nbr"
    # Registry values, not the ProcessingConfig defaults (0.4).
    assert change["display_range"] == pytest.approx(INDICES["nbr"].change_display_range)
    assert change["delta_threshold"] == pytest.approx(INDICES["nbr"].change_delta_threshold)
    # June -> July is a synthetic burn: NBR drops everywhere.
    assert change["stats"]["pct_decreased"] == pytest.approx(100.0)
    assert change["stats"]["delta_mean"] == pytest.approx(-1.1, abs=1e-2)
    assert "burn" in change["note"]
    assert "does not by itself establish causes" in change["note"]

    provenance = json.loads(blob.uploads[f"{prefix}/provenance.json"])
    assert provenance["schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert provenance["processing"]["operation"] == "nbr"
    assert provenance["processing"]["index"]["formula"] == "(NIR - SWIR2) / (NIR + SWIR2)"
    assert provenance["processing"]["index"]["band_roles"] == {"nir": "B08", "swir": "B12"}
    assert provenance["change"]["operation"] == "nbr"
    # The SWIR resampling caveat reaches every scene's warnings.
    assert any("SWIR" in w for scene in provenance["scenes"] for w in scene["warnings"])


async def test_ndvi_analysis_unchanged(monkeypatch, tmp_path):
    """The NDVI path keeps its artifact types, names, and change semantics."""
    outcome, session, blob = await _run_fake_pipeline(
        monkeypatch, tmp_path, _ndvi_candidates(tmp_path / "scenes"), "ndvi"
    )
    assert outcome.status == "succeeded", outcome.detail

    artifact_types = {a.artifact_type for a in _added(session, Artifact)}
    assert ArtifactType.NDVI_COG in artifact_types
    assert ArtifactType.NDVI_CHANGE_COG in artifact_types
    assert ArtifactType.NBR_COG not in artifact_types

    prefix = f"analyses/{_fake_id(session)}"
    assert f"{prefix}/scenes/{JUNE_ID}/ndvi.tif" in blob.uploads
    assert f"{prefix}/ndvi_change.tif" in blob.uploads

    summary = json.loads(blob.uploads[f"{prefix}/summary.json"])
    change = summary["change"]
    assert change["operation"] == "ndvi"
    assert change["display_range"] == pytest.approx(0.4)
    assert change["note"] == INDICES["ndvi"].change_note
    assert change["stats"]["pct_decreased"] == pytest.approx(0.0)

    provenance = json.loads(blob.uploads[f"{prefix}/provenance.json"])
    assert provenance["processing"]["index"]["band_roles"] == {"red": "B04", "nir": "B08"}


async def test_unknown_operation_is_terminal_user_input(monkeypatch, tmp_path):
    """An unregistered operation must fail before any processing starts."""
    monkeypatch.setattr(runner, "search_scenes", lambda *a, **k: None)
    analysis = _fake_analysis("evi")
    with pytest.raises(UserInputError, match="Unknown operation"):
        await runner._run_pipeline(
            _FakeSession(),  # type: ignore[arg-type]
            analysis,
            Settings(_env_file=None),
            _FakeBlob(),  # type: ignore[arg-type]
            WorkerMetrics(),
            time.monotonic() + 3600,
        )


def _fake_id(session: _FakeSession) -> str:
    """The analysis id, recovered from any recorded row."""
    row = session.added[0]
    return str(row.analysis_id)


# ---------------------------------------------------------------------------
# FIRMS active-fire overlay
# ---------------------------------------------------------------------------

FIRE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [23.712, 38.963]},
            "properties": {"acq_date": "2024-07-15", "acq_time": "1235", "frp": 45.7},
        }
    ],
}


def _firms_result(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "geojson": FIRE_GEOJSON,
        "detection_count": len(FIRE_GEOJSON["features"]),
        "source": "VIIRS_SNPP_SP",
        "start_date": "2024-06-01",
        "end_date": "2024-07-31",
        "windows_queried": 11,
        "windows_total": 11,
        "truncated": False,
    }
    return SimpleNamespace(**(base | overrides))


def _firms_settings() -> Settings:
    return Settings(_env_file=None, firms_map_key="test-key")


async def test_fire_detections_uploaded_and_in_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "fetch_fire_detections", lambda **kwargs: _firms_result())
    outcome, session, blob = await _run_fake_pipeline(
        monkeypatch,
        tmp_path,
        _nbr_candidates(tmp_path / "scenes"),
        "nbr",
        settings=_firms_settings(),
    )
    assert outcome.status == "succeeded", outcome.detail

    artifact_types = {a.artifact_type for a in _added(session, Artifact)}
    assert ArtifactType.FIRE_DETECTIONS in artifact_types

    prefix = f"analyses/{_fake_id(session)}"
    geojson = json.loads(blob.uploads[f"{prefix}/fire_detections.geojson"])
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1
    assert geojson["features"][0]["geometry"]["coordinates"] == [23.712, 38.963]

    provenance = json.loads(blob.uploads[f"{prefix}/provenance.json"])
    fire = provenance["fire_context"]
    assert fire["source"] == "VIIRS_SNPP_SP"
    assert fire["detection_count"] == 1
    assert fire["windows_queried"] == 11
    assert fire["windows_total"] == 11
    assert fire["truncated"] is False
    assert fire["start_date"] == "2024-06-01"
    assert fire["end_date"] == "2024-07-31"
    assert "FIRMS" in fire["note"]


async def test_firms_failure_degrades_to_warning(monkeypatch, tmp_path):
    def boom(**kwargs: Any) -> Any:
        raise FirmsError("transaction over-limit")

    monkeypatch.setattr(runner, "fetch_fire_detections", boom)
    outcome, session, blob = await _run_fake_pipeline(
        monkeypatch,
        tmp_path,
        _nbr_candidates(tmp_path / "scenes"),
        "nbr",
        settings=_firms_settings(),
    )
    # The overlay is context only: its failure must not fail the analysis.
    assert outcome.status == "succeeded", outcome.detail
    artifact_types = {a.artifact_type for a in _added(session, Artifact)}
    assert ArtifactType.FIRE_DETECTIONS not in artifact_types

    prefix = f"analyses/{_fake_id(session)}"
    provenance = json.loads(blob.uploads[f"{prefix}/provenance.json"])
    assert "fire_context" not in provenance
    assert any("FIRMS" in w for w in provenance["warnings"])


async def test_firms_skipped_silently_without_key(monkeypatch, tmp_path):
    called = False

    def spy(**kwargs: Any) -> Any:
        nonlocal called
        called = True
        return _firms_result()

    monkeypatch.setattr(runner, "fetch_fire_detections", spy)
    outcome, session, blob = await _run_fake_pipeline(
        monkeypatch,
        tmp_path,
        _nbr_candidates(tmp_path / "scenes"),
        "nbr",
    )
    assert outcome.status == "succeeded", outcome.detail
    assert called is False  # no key -> the API is never contacted
    artifact_types = {a.artifact_type for a in _added(session, Artifact)}
    assert ArtifactType.FIRE_DETECTIONS not in artifact_types

    prefix = f"analyses/{_fake_id(session)}"
    provenance = json.loads(blob.uploads[f"{prefix}/provenance.json"])
    assert "fire_context" not in provenance
    assert not any("FIRMS" in w for w in provenance["warnings"])
