"""Worker unit tests that require no external services."""

from __future__ import annotations

import pytest

from earth_observation.errors import DataError
from oeop_core.settings import Settings
from oeop_worker.runner import _software_metadata, _StorageBudget


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
