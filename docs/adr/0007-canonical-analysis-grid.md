# ADR 0007: Canonical analysis grid and acquisition-level mosaicking

* Status: Accepted
* Date: 2026-08-03
* Supersedes parts of [ADR 0004](0004-native-utm-processing.md)

## Context

A production analysis over the Detroit Urban Core region
(`b4b9935e-5123-41e9-a58b-22a57811dc75`) produced previews with visibly
different extents: some dates covered only the northern portion of the area of
interest, others reached the Detroit River. Auditing the artifacts showed this
was **not a presentation problem**.

The AOI straddles the boundary between Sentinel-2 MGRS tiles **T17TLG** and
**T17TLH**. A single acquisition is distributed as one STAC item per tile, so
the catalog returned two items for the same observation instant — one covering
100 % of the AOI, one covering 56.2 %. Of 24 acquisitions in the requested
window, **13 had both granules available**.

The v1 pipeline:

1. selected **one STAC item** per temporal bucket, requiring only 25 % AOI
   overlap, so a 56 %-coverage granule was accepted as a whole observation;
2. processed each scene in **its own native CRS**, clipped with
   `clip_box`, which silently intersects the requested window with the
   granule's own extent instead of failing.

The result: rasters of 1272×627 for T17TLH dates and 1272×1149 for T17TLG
dates, and NDVI statistics computed over **751,081 pixels versus 1,372,771
pixels** — different ground. Any change reported between two such dates
conflated a real vegetation signal with a change of measurement area.

Analyses spanning a UTM zone boundary (the Southeast Michigan demonstration
region mixes T16TGN and T17TLH) additionally produced outputs in **different
CRSs**, compounding the problem.

## Decision

Each analysis derives exactly **one canonical grid** from its AOI, and every
observation is reprojected onto that grid.

**Grid derivation** (`earth_observation/grid.py`)

* CRS: the WGS84 UTM zone containing the AOI centroid. UTM is the native CRS of
  Sentinel-2 assets (so the common case is a near-identity reprojection), is
  metric, and has low distortion within a zone. The AOI is always retained in
  EPSG:4326 for the API and provenance.
* Resolution: 10 m, the native GSD of the red and NIR bands (configurable).
* Bounds: the projected AOI bounds snapped **outward** to the resolution
  lattice anchored at the CRS origin, so overlapping analyses are
  co-registered rather than merely internally consistent.
* Persisted: CRS, resolution, affine transform, width, height, projected and
  geographic bounds, AOI geometry, and a `schema_version`.

**Acquisition grouping** (`earth_observation/acquisition.py`)

Granules are grouped into acquisitions by observation time (rounded to the
minute), platform, relative orbit, and collection. The tile id and the
*processing* timestamp are deliberately excluded from the key — granules of one
acquisition are frequently processed at different times, which is precisely why
that field must not split them.

**Mosaicking** (`earth_observation/mosaic.py`)

Every granule intersecting the grid is read over its window only (COG range
reads) and reprojected onto the canonical grid. Overlaps resolve by
**first-valid-by-item-id**: deterministic, and scientifically equivalent since
overlapping pixels of one acquisition observe the same ground at the same
instant. Spectral bands use **bilinear**; the Scene Classification Layer uses
**nearest**, because averaging categorical class labels would invent classes
that do not exist.

**Coverage gate**

Geometric AOI coverage is computed per acquisition; anything below
`min_aoi_coverage_pct` (default **99 %**, configurable) is marked unusable
with reason `insufficient_aoi_coverage`. Coverage is checked *before* cloud
statistics, because a partially observed date is not comparable to a fully
observed one no matter how clean its pixels are.

Coverage accounting classifies every AOI pixel exactly once: uncovered →
nodata → cloud/shadow/cirrus → snow → other masked → invalid spectral → valid.

## Consequences

**Positive**

* Every usable observation of an analysis shares one CRS, transform, width,
  height, bounds, and AOI mask **by construction**. The worker additionally
  refuses to publish an analysis whose observations disagree.
* AOIs crossing tile *or UTM zone* boundaries are handled correctly.
* Statistics are always computed over the identical footprint, so a reported
  change reflects vegetation, not geometry.
* Previews share pixel dimensions and map extent, making before/after
  comparison meaningful; "no source imagery" renders in a distinct grey.
* Provenance records the grid, per-acquisition coverage, and **every**
  contributing STAC item and tile.

**Negative / costs**

* One reprojection step per band per granule that v1 avoided. For a same-zone
  AOI this is close to a no-op; across a zone boundary it is genuinely needed.
* Bilinear resampling of spectral bands is a mild smoothing of the source
  grid. NDVI is a ratio of two bands resampled identically, so the index is
  not systematically biased, but per-pixel values near sharp boundaries differ
  slightly from nearest-neighbour sampling. Documented in the methodology.
* Multi-granule acquisitions read more data (still windowed).
* Stricter coverage rejects dates v1 would have (wrongly) accepted, so an
  analysis may return fewer observations. This is the intended trade:
  fewer, comparable observations rather than more, incomparable ones.

**Compatibility**

* `PROCESSING_VERSION` → **2.0.0**; provenance schema → **2.0.0**;
  selection algorithm → **2.0.0**. Results from 1.x are **not comparable**
  with 2.x for AOIs that cross tile boundaries.
* Analyses stored before this change have `grid = null`; the API returns that
  honestly and the UI labels them as predating the guarantee.
