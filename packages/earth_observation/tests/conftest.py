"""Shared fixtures for the science test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from earth_observation.testing import build_synthetic_scene


@pytest.fixture
def synthetic_scene(tmp_path: Path) -> dict:
    return build_synthetic_scene(tmp_path / "scene")
