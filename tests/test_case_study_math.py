"""Every equation in the published documents must actually render.

LaTeX that `latex2mathml` cannot parse does not raise — it leaks the unhandled
control sequence into the output as literal text. A `\\\\[4pt]` row separator,
valid LaTeX and fine on GitHub, rendered as the visible string "[4pt]" in the
middle of an equation in the PDF. These tests fail on that class of silent
degradation rather than leaving it to be spotted by eye.
"""

from __future__ import annotations

import html as html_lib
import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Every document that contains math, discovered rather than listed — a new
#: equation in a doc nobody remembered to enumerate is exactly the case that
#: would otherwise ship unrendered.
DOCS = sorted(
    path for path in (REPO_ROOT / "docs").rglob("*.md") if "$" in path.read_text(encoding="utf-8")
)

_spec = importlib.util.spec_from_file_location(
    "build_case_study_pdf", REPO_ROOT / "scripts" / "build_case_study_pdf.py"
)
assert _spec and _spec.loader
_builder = importlib.util.module_from_spec(_spec)

#: Leaked LaTeX has to be searched for in the *rendered text*, not the MathML
#: source. The converter splits it across elements — `\\[4pt]` comes out as
#: `<mo>[</mo><mn>4pt</mn><mo>]</mo>` — so a pattern applied to the markup
#: finds nothing while the reader plainly sees "[4pt]".
_LEAKED = re.compile(r"\[\s*\d+\s*(?:pt|em|ex|mu)\s*\]|\\[a-zA-Z]+|\\\\")
_TAG = re.compile(r"<[^>]+>")


def _text_content(mathml: str) -> str:
    """The characters a reader actually sees, with entities decoded."""
    return html_lib.unescape(_TAG.sub("", mathml))


def _load():
    try:
        _spec.loader.exec_module(_builder)  # type: ignore[union-attr]
    except ImportError as exc:  # pragma: no cover - optional render deps
        pytest.skip(f"PDF build dependencies unavailable: {exc}")
    return _builder


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_equation_converts_to_mathml(doc: Path) -> None:
    builder = _load()
    _, rendered = builder._extract_math(doc.read_text(encoding="utf-8"))

    for index, mathml in enumerate(rendered):
        assert "<math" in mathml, f"{doc.name} equation {index} produced no MathML"
        leaked = _LEAKED.findall(_text_content(mathml))
        assert not leaked, (
            f"{doc.name} equation {index} contains unconverted LaTeX {leaked}. "
            "latex2mathml passes unsupported commands through as literal text, "
            "so this would appear verbatim in the rendered PDF."
        )


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_math_delimiters_are_balanced(doc: Path) -> None:
    """An unclosed `$` silently swallows a paragraph into an equation."""
    builder = _load()
    text = doc.read_text(encoding="utf-8")
    stripped, _ = builder._extract_math(text)
    # Code spans and fences are restored by _extract_math, so strip them again
    # before counting; a `$` inside one is shell syntax, not mathematics.
    stripped = builder._FENCE.sub("", stripped)
    stripped = builder._CODE_SPAN.sub("", stripped)
    assert "$" not in stripped, (
        f"{doc.name} has unmatched '$' after math extraction — an unbalanced "
        "delimiter, which would render as literal text or consume prose."
    )
