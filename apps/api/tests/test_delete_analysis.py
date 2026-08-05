"""Safety rules for the destructive `oeop-admin delete-analysis` command.

Deleting an analysis removes real scientific outputs, so the selection logic
must be precise. These tests pin the two mistakes that are easy to make:
sweeping up work that is merely queued, and treating "no grid" as "legacy".
"""

from __future__ import annotations

import pytest

from oeop_api.cli import GRID_MAJOR_VERSION, _major_version


class TestMajorVersionParsing:
    """`--legacy` keys on the processing generation, not on grid presence.

    A queued analysis has no grid yet either; keying on `grid IS NULL` would
    delete work in flight.
    """

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("1.0.0", 1),
            ("2.0.0", 2),
            ("2.1.3", 2),
            ("10.0.0", 10),
        ],
    )
    def test_parses_major_component(self, version: str, expected: int) -> None:
        assert _major_version(version) == expected

    @pytest.mark.parametrize("version", [None, "", "not-a-version", "v2"])
    def test_unparseable_versions_read_as_legacy(self, version: str | None) -> None:
        """Unknown provenance is treated as pre-grid, never as current."""
        assert _major_version(version) < GRID_MAJOR_VERSION

    def test_current_generation_is_not_legacy(self) -> None:
        assert _major_version("2.0.0") >= GRID_MAJOR_VERSION

    def test_pre_grid_generation_is_legacy(self) -> None:
        assert _major_version("1.0.0") < GRID_MAJOR_VERSION

    def test_future_generations_are_not_legacy(self) -> None:
        """A 3.x analysis is newer than the grid, so it must never be swept up."""
        assert _major_version("3.0.0") >= GRID_MAJOR_VERSION
