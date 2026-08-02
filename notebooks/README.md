# Notebooks

Interactive, reproducible companions to the platform. They import the exact
production science package (`packages/earth_observation`) — no
reimplementation — so what you see here is what the worker computes.

| Notebook | Purpose |
| --- | --- |
| `ndvi_southeast_michigan.ipynb` | Discover, select, and process one Sentinel-2 scene over the Southeast Michigan demonstration region; display NDVI and true color; inspect statistics and provenance. |

## How to run

From the repository root:

```bash
uv sync
uv run jupyter lab notebooks/
```

Requirements: Python 3.12 via uv (no Azure account needed) and network
access to the Microsoft Planetary Computer (STAC API and asset reads).

Outputs (NDVI COGs, preview PNGs, scene summaries) land in
`notebooks/outputs/`, which is gitignored — nothing you run here dirties the
repository.

## Attribution

Contains modified Copernicus Sentinel data, processed by ESA, accessed via
the Microsoft Planetary Computer.

Before interpreting results, read
[`docs/scientific-methodology.md`](../docs/scientific-methodology.md) and
[`docs/limitations.md`](../docs/limitations.md).
