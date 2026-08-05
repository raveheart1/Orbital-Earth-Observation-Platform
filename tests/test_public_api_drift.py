"""Guard against the notebook and scripts drifting from the package API.

The v2 refactor renamed ``select_scenes`` -> ``select_acquisitions`` and
``process_scene`` -> ``process_acquisition``. Both the reproducibility
notebook and the live smoke test kept calling the old names and broke
silently, because neither is executed by the default test suite (the notebook
and smoke test need network access) and neither was type-checked.

These tests close that gap WITHOUT needing the network: they statically parse
every ``earth_observation`` / ``oeop_*`` import in ``notebooks/`` and
``scripts/`` and assert the symbol still exists. A rename that forgets these
callers now fails in CI.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((REPO_ROOT / "notebooks").glob("*.ipynb"))
SCRIPTS = sorted((REPO_ROOT / "scripts").glob("*.py"))

#: Only first-party packages are checked; third-party APIs are pinned by the
#: lockfile and covered by their own releases.
FIRST_PARTY = ("earth_observation", "oeop_core", "oeop_api", "oeop_worker")


def _notebook_code(path: Path) -> str:
    notebook = json.loads(path.read_text())
    sources: list[str] = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        # Skip IPython magics/shell escapes, which are not valid Python.
        lines = [ln for ln in source.split("\n") if not ln.lstrip().startswith(("%", "!"))]
        sources.append("\n".join(lines))
    return "\n".join(sources)


def _first_party_imports(code: str, origin: str) -> list[tuple[str, str]]:
    """Return (module, symbol) pairs imported from first-party packages."""
    tree = ast.parse(code, filename=origin)
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FIRST_PARTY:
                for alias in node.names:
                    found.append((node.module, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FIRST_PARTY:
                    found.append((alias.name, ""))
    return found


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_code_cells_parse(path: Path) -> None:
    ast.parse(_notebook_code(path), filename=str(path))


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_imports_exist(path: Path) -> None:
    imports = _first_party_imports(_notebook_code(path), str(path))
    assert imports, f"{path.name} imports nothing from the platform packages"
    _assert_symbols_exist(imports, path)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_script_imports_exist(path: Path) -> None:
    imports = _first_party_imports(path.read_text(), str(path))
    _assert_symbols_exist(imports, path)


def _assert_symbols_exist(imports: list[tuple[str, str]], origin: Path) -> None:
    for module_name, symbol in imports:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:  # pragma: no cover - failure path
            pytest.fail(f"{origin.name} imports missing module '{module_name}': {exc}")
        if symbol and not hasattr(module, symbol):
            pytest.fail(
                f"{origin.name} imports '{symbol}' from '{module_name}', which no "
                "longer exists. Update the notebook/script to the current API."
            )


def test_notebook_does_not_use_removed_v1_api() -> None:
    """Explicit guard for the exact names that broke."""
    removed = ("select_scenes", "process_scene", "min_aoi_overlap_pct")
    offenders: list[str] = []
    for path in [*NOTEBOOKS, *SCRIPTS]:
        code = _notebook_code(path) if path.suffix == ".ipynb" else path.read_text()
        for name in removed:
            if name in code:
                offenders.append(f"{path.name}: {name}")
    assert not offenders, "These files still reference the pre-2.0.0 API: " + ", ".join(offenders)
