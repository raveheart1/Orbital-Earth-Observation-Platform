"""Loader for the predefined region catalog shipped with the platform."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_predefined_regions() -> list[dict[str, Any]]:
    """Read the packaged region definitions (name, slug, description, bbox)."""
    package_files = resources.files("oeop_core.data")
    raw = (package_files / "regions.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    regions: list[dict[str, Any]] = data["regions"]
    return regions
