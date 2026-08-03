# Audit: spatial comparability defect (2026-08-03)

Audit of analysis **`b4b9935e-5123-41e9-a58b-22a57811dc75`** (Detroit Urban
Core), which produced earliest/latest previews with different spatial extents
and different image heights.

**Verdict: a genuine scientific-processing defect, not a presentation issue.**
The reported NDVI change for this analysis is **invalid** and must not be
cited.

## Root cause

The Detroit Urban Core AOI (`-83.15, 42.30, -83.00, 42.40`) straddles the
boundary between Sentinel-2 MGRS tiles **T17TLG** and **T17TLH**. One
acquisition is published as one STAC item per tile:

* T17TLG granules cover **100 %** of the AOI,
* T17TLH granules cover **56.2 %** (northern portion only),
* **13 of 24** acquisitions in the requested window had *both* granules
  available — the data for full coverage existed and was discarded.

Processing version 1.x selected a single STAC item per temporal bucket and
required only 25 % AOI overlap, so a 56 %-coverage granule was accepted as a
complete observation. The raster read then used `clip_box`, which silently
intersects the requested window with the granule's own extent rather than
failing.

## What was affected

| Layer | Affected | Evidence |
| --- | --- | --- |
| **Scene selection** | **Yes — root cause** | 13 multi-granule acquisitions collapsed to one granule each |
| **Analytical COGs** | **Yes** | T17TLH dates: 1272×627; T17TLG dates: 1272×1149 (same transform origin, different extent) |
| **NDVI statistics** | **Yes** | AOI pixel count 751,081 (T17TLH) vs 1,372,771 (T17TLG) — statistics computed over different ground |
| **Selected-scene coverage** | **Yes** | `aoi_overlap_pct = 56.2` was recorded, but the scene was still marked usable and included in the series |
| **Provenance** | **Yes (incomplete)** | recorded one item id per observation; no canonical grid, no coverage accounting, no contributing-granule list |
| **Preview PNGs** | Yes (downstream) | previews inherit the truncated COG grid; nothing was wrong in preview generation itself |
| **Frontend display** | No (symptom only) | the UI faithfully rendered images that genuinely differed in size |

## Quantified error

Reprocessing the same region and date range with the corrected pipeline
(processing version 2.0.0) isolates the error, because full-coverage dates
should be unchanged and partial-coverage dates should move:

| Acquisition | v1 coverage | v1 mean NDVI | v2 mean NDVI | Change |
| --- | --- | --- | --- | --- |
| 2026-02-27 (T17TLG) | 100 % | 0.1574 | **0.1574** | **0.0000** — unchanged, as expected |
| 2026-05-30 (T17TLH) | 56.2 % | 0.4233 | **0.3671** | **−0.0562** — v1 was inflated |

The full-coverage date reproduces **exactly**, confirming the correction is
targeted rather than a wholesale change in the science. The partial-coverage
date moved by −0.056 because v1 measured only the northern 56 % of the AOI,
which is greener and less densely built than the riverfront it omitted.

Since the v1 series interleaved 56 %-coverage and 100 %-coverage dates, its
date-to-date differences mixed a real vegetation signal with a change of
measurement area of comparable magnitude. **The −0.053 earliest-to-latest
difference previously reported for this analysis is not a valid measurement.**

## Corrected result

Reprocessed Detroit Urban Core (2025-09-01 → 2026-06-30, cloud ≤ 20 %, limit 6):

* Canonical grid `EPSG:32617`, 1264×1141 px @ 10 m.
* **All six** observations: `aoi_pixel_count = 1,372,771`, coverage **100 %**.
* Four of six are mosaics of two granules (T17TLG + T17TLH); ten contributing
  STAC items are recorded in provenance.
* Four acquisitions rejected with `insufficient_aoi_coverage` — exactly the
  single-granule T17TLH dates v1 would have accepted.
* One distinct COG geometry, one distinct preview size (632×571), one
  artifact grid signature.

## Why existing tests missed it

The synthetic fixtures used a single scene whose extent fully contained the
AOI, so the truncation path was never exercised. The suite now includes
adjacent-granule fixtures (`build_adjacent_granules`) that reproduce a
tile-crossing AOI, plus assertions that no seam or nodata gap appears, that
partial-coverage acquisitions are rejected, and that COG geometry, preview
dimensions and AOI pixel counts are identical across dates
(`tests/test_spatial_comparability.py`).

## Disposition of the affected analysis

`b4b9935e-5123-41e9-a58b-22a57811dc75` was produced by processing version
1.0.0 and is retained for audit purposes. It reports `grid: null` through the
API, and the interface labels it as predating the canonical-grid guarantee.
It should be re-run rather than cited.

See [ADR 0007](adr/0007-canonical-analysis-grid.md) for the architecture that
prevents recurrence.
