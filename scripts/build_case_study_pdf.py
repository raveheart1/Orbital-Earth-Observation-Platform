"""Render a Markdown document to a print-ready PDF.

Uses the Chromium that Playwright already installs for the end-to-end tests, so
no additional PDF toolchain (pandoc, weasyprint, wkhtmltopdf) is required.

    uv run python scripts/build_case_study_pdf.py docs/case-study.md

Writes alongside the source, e.g. docs/case-study.pdf.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

# Print stylesheet: serif body for long-form reading, monospace for data, and
# table/heading rules that survive page breaks.
CSS = """
@page { size: A4; margin: 20mm 18mm; }
* { box-sizing: border-box; }
body {
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; max-width: none; margin: 0;
}
h1, h2, h3, h4 { font-family: inherit; color: #0f3d3d; line-height: 1.25; }
h1 { font-size: 21pt; margin: 0 0 .2em; border-bottom: 2px solid #0f3d3d; padding-bottom: .25em; }
h2 { font-size: 15pt; margin: 1.6em 0 .5em; border-bottom: 1px solid #cfd8d8; padding-bottom: .2em;
     break-after: avoid; }
h3 { font-size: 12pt; margin: 1.2em 0 .4em; break-after: avoid; }
h4 { font-size: 10.5pt; margin: 1em 0 .3em; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
blockquote {
  margin: 1em 0; padding: .5em 1em; border-left: 3px solid #0f3d3d;
  background: #f4f7f7; font-style: italic;
}
code, pre { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 9pt; }
code { background: #f0f3f3; padding: .1em .3em; border-radius: 3px; }
pre {
  background: #f7f9f9; border: 1px solid #dfe6e6; border-radius: 4px;
  padding: .8em 1em; overflow-x: auto; line-height: 1.4; break-inside: avoid;
}
pre code { background: none; padding: 0; }
table {
  border-collapse: collapse; width: 100%; margin: 1em 0;
  font-size: 9pt; break-inside: avoid;
}
th, td { border: 1px solid #d5dede; padding: .4em .6em; text-align: left; vertical-align: top; }
th { background: #eef3f3; font-weight: 600; }
tr:nth-child(even) td { background: #fafcfc; }
hr { border: none; border-top: 1px solid #cfd8d8; margin: 1.8em 0; }
a { color: #0f3d3d; text-decoration: none; border-bottom: 1px solid #9fc0c0; }
em { color: #333; }
strong { color: #0a2e2e; }
img { max-width: 100%; }
"""

RENDER_JS = """
const {{ chromium }} = require('@playwright/test');
(async () => {{
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://{html}', {{ waitUntil: 'load' }});
  await page.pdf({{
    path: '{pdf}',
    format: 'A4',
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate:
      '<div style="width:100%;font-size:8pt;color:#777;padding:0 18mm;' +
      'font-family:Georgia,serif;display:flex;justify-content:space-between;">' +
      '<span>{title}</span><span class="pageNumber"></span></div>',
    margin: {{ top: '18mm', bottom: '18mm', left: '18mm', right: '18mm' }},
  }});
  await browser.close();
}})();
"""


def build(source: Path) -> Path:
    text = source.read_text(encoding="utf-8")
    title = next(
        (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")),
        source.stem,
    )
    body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "toc", "attr_list", "sane_lists"]
    )
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>"
    )

    # Absolute: node runs with cwd=apps/web so a relative path would land there.
    pdf_path = source.resolve().with_suffix(".pdf")
    web_dir = Path(__file__).resolve().parents[1] / "apps" / "web"
    script = web_dir / ".render-pdf.tmp.cjs"
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "doc.html"
        html_path.write_text(html, encoding="utf-8")
        script.write_text(
            RENDER_JS.format(html=html_path, pdf=pdf_path, title=title.replace("'", "\\'")),
            encoding="utf-8",
        )
        try:
            result = subprocess.run(
                ["node", str(script)], cwd=web_dir, capture_output=True, text=True, check=False
            )
        finally:
            script.unlink(missing_ok=True)
        if result.returncode != 0:
            raise SystemExit(
                "PDF render failed. Playwright's Chromium is required:\n"
                "  cd apps/web && pnpm exec playwright install chromium\n\n"
                f"{result.stderr[-800:]}"
            )
    return pdf_path


def main() -> None:
    sources = [Path(a) for a in sys.argv[1:]] or [Path("docs/case-study.md")]
    for source in sources:
        if not source.exists():
            raise SystemExit(f"No such file: {source}")
        pdf = build(source)
        size_kb = pdf.stat().st_size / 1024
        print(f"  {source} -> {pdf} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
