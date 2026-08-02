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
