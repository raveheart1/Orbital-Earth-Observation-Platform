"""Assert that synthetic satellite data cannot reach a deployed environment.

The platform's rule is that synthetic imagery is permitted in automated tests
ONLY — never in the running application. ``earth_observation.testing``
generates fake Sentinel-2-like rasters, so it must not be present in the
artifacts that get deployed.

Enforcement has three layers:

1. The wheel excludes ``testing.py`` (``packages/earth_observation/pyproject.toml``).
   Container images build with ``uv sync --no-editable``, so they install that
   wheel and the module is physically absent from them.
2. These tests assert the exclusion is configured and that no production module
   imports the fixtures.
3. The CI ``docker`` job greps the built images (see ``.github/workflows/ci.yml``).

Tests import the module straight from ``src/`` via the editable dev install, so
excluding it from the wheel costs the test suite nothing.
"""

from __future__ import annotations

import ast
import glob
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCIENCE_PKG = REPO_ROOT / "packages" / "earth_observation"

#: Modules that ship to production. Anything importable here must be real.
PRODUCTION_SOURCE_DIRS = [
    SCIENCE_PKG / "src",
    REPO_ROOT / "packages" / "platform_core" / "src",
    REPO_ROOT / "apps" / "api" / "src",
    REPO_ROOT / "apps" / "worker" / "src",
]

#: Names that only ever belong to synthetic-fixture code.
SYNTHETIC_SYMBOLS = (
    "build_synthetic_scene",
    "build_adjacent_granules",
    "make_file_candidate",
    "make_metadata_candidate",
    "write_raster",
)


def test_wheel_excludes_the_synthetic_data_module() -> None:
    """The build config must exclude the fixture generator from the wheel."""
    config = tomllib.loads((SCIENCE_PKG / "pyproject.toml").read_text())
    excluded = config["tool"]["hatch"]["build"]["targets"]["wheel"].get("exclude", [])
    assert "src/earth_observation/testing.py" in excluded, (
        "earth_observation.testing generates synthetic satellite rasters and must "
        "be excluded from the wheel so it never ships to a deployed environment."
    )


def test_built_wheel_contains_no_synthetic_data_module() -> None:
    """Actually build the wheel and inspect it — config can lie, artifacts cannot."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on PATH; the wheel-content check needs it")
    with tempfile.TemporaryDirectory() as out:
        result = subprocess.run(
            [uv, "build", "--package", "earth-observation", "--wheel", "--out-dir", out],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,  # handled below so the failure message is useful
        )
        if result.returncode != 0:
            pytest.fail(f"uv build failed:\n{result.stderr[-500:]}")
        wheels = glob.glob(f"{out}/*.whl")
        assert wheels, "no wheel produced"
        names = zipfile.ZipFile(wheels[0]).namelist()
    offenders = [n for n in names if "testing" in n]
    assert not offenders, f"Synthetic-data module leaked into the distributable wheel: {offenders}"


def _iter_production_modules():
    for root in PRODUCTION_SOURCE_DIRS:
        for path in root.rglob("*.py"):
            if path.name == "testing.py":
                continue  # the fixture module itself, excluded from the wheel
            yield path


def test_no_production_module_imports_the_fixtures() -> None:
    """A production import of the fixtures would defeat the wheel exclusion."""
    offenders: list[str] = []
    for path in _iter_production_modules():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.endswith("earth_observation.testing"):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.endswith("earth_observation.testing"):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}: {alias.name}")
    assert not offenders, "Production code imports synthetic fixtures: " + ", ".join(offenders)


def test_no_production_module_references_synthetic_builders() -> None:
    """Catch a copy-pasted fixture builder even without the import."""
    offenders: list[str] = []
    for path in _iter_production_modules():
        text = path.read_text()
        for symbol in SYNTHETIC_SYMBOLS:
            if symbol in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {symbol}")
    assert not offenders, "Production code references synthetic-fixture builders: " + ", ".join(
        offenders
    )


def test_demo_bundle_is_not_copied_into_container_images() -> None:
    """The committed demo bundle is real derived data, but deployments must
    process live imagery rather than import a precomputed bundle."""
    for dockerfile in (
        REPO_ROOT / "apps" / "api" / "Dockerfile",
        REPO_ROOT / "apps" / "worker" / "Dockerfile",
    ):
        copies = [
            line
            for line in dockerfile.read_text().splitlines()
            if line.startswith("COPY") and " data" in line
        ]
        assert not copies, f"{dockerfile.name} copies data/ into the image: {copies}"
