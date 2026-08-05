# Scientific methodology

This document specifies exactly what the platform measures, how, and where the
science can go wrong. It is organized as a chain:

**source observations → calculated measurements → interpretation →
uncertainty → limitations**

Each link is documented so a reader can audit any number the platform
produces. The implementation lives in `packages/earth_observation`; every
parameter described here is captured verbatim in the provenance document of
each run (see [data-provenance.md](data-provenance.md)).

Related: [architecture.md](architecture.md) for where this runs,
[limitations.md](limitations.md) for what the results do *not* show.

---

## 1. Source observations

**Dataset:** Sentinel-2 Level-2A (atmospherically corrected surface
reflectance), produced by the European Space Agency under the Copernicus
program, accessed through the Microsoft Planetary Computer STAC API
(`https://planetarycomputer.microsoft.com/api/stac/v1`, collection
`sentinel-2-l2a`).

> Contains modified Copernicus Sentinel data, processed by ESA, accessed via
> the Microsoft Planetary Computer.

**Assets read per scene** (`earth_observation/stac.py`,
`earth_observation/processing.py`):

| Asset | Band | Resolution | Use |
| --- | --- | --- | --- |
| `B04` | Red (~665 nm) | 10 m | NDVI denominator/numerator |
| `B08` | NIR (~842 nm) | 10 m | NDVI numerator/denominator |
| `SCL` | Scene Classification Layer | 20 m | Pixel quality masking |
| `visual` | True Color Image (TCI) | 10 m | Human-readable preview only |

Only the raster window covering the AOI is read (HTTP range reads against
cloud-optimized GeoTIFFs); full scenes are never downloaded.

A single acquisition is distributed as **one item per MGRS tile**, so an AOI
that crosses a tile boundary matches several items for the same observation
instant. All of them are read and mosaicked (§2.5). Every asset is reprojected
onto the analysis-wide **canonical grid** (§2.4) — the 20 m SCL with
nearest-neighbor resampling, because its values are class labels and any
interpolating resampler would invent meaningless intermediate classes.

The grid CRS is the UTM zone of the AOI centroid, so for most AOIs this remains
the scenes' native CRS ([ADR 0004](adr/0004-native-utm-processing.md),
[ADR 0007](adr/0007-canonical-analysis-grid.md)).

---

## 2. Calculated measurements

### 2.1 Digital numbers → reflectance (the baseline-offset pitfall)

Sentinel-2 L2A distributes reflectance as scaled integers ("digital numbers",
DN). The conversion is:

```
reflectance = DN × scale + offset
```

with `scale = 1e-4`. Since **processing baseline 04.00** (scenes processed on
or after 25 January 2022), ESA changed the encoding to `DN' = DN + 1000`, so
the correct conversion becomes:

```
reflectance = DN × 1e-4 + (−0.1)        for baseline ≥ 04.00
reflectance = DN × 1e-4                 for earlier baselines
```

**Why this matters for NDVI specifically:** NDVI is a ratio, so a common
*multiplicative* scale cancels:

```
NDVI = (NIR − Red) / (NIR + Red)
```

But an *additive* offset does **not** cancel — with the offset ignored, both
numerator differences and denominator sums are shifted, and NDVI is
materially biased. Mixing pre- and post-04.00 scenes in one time series
without offset handling would create a spurious "change" at the baseline
boundary that has nothing to do with vegetation.

The implementation (`earth_observation/ndvi.py:resolve_band_scaling`) picks
the conversion in priority order:

1. `raster:bands` scale/offset from STAC asset metadata, when present
   (`source: "raster_ext"`).
2. Heuristic on `s2:processing_baseline`: ≥ 04.00 → offset −0.1
   (`source: "baseline_heuristic"`).
3. The pre-04.00 default: scale 1e-4, offset 0 (`source: "default"`).

The chosen scaling and its source are recorded per scene in provenance.

### 2.2 SCL mask policy

Each Sentinel-2 L2A scene ships a Scene Classification Layer. The platform
masks (sets to NaN) pixels in classes where the reflectance is not a valid
observation of the land surface, and retains classes that are real surface
observations even when they look unusual. The policy is configurable and the
exact class list used is stored with every run; the defaults
(`earth_observation/types.py:DEFAULT_MASKED_SCL_CLASSES`) are:

| SCL | Name | Policy | Rationale |
| --- | --- | --- | --- |
| 0 | NO_DATA | **Masked** | No measurement exists; any value is fill. |
| 1 | SATURATED_OR_DEFECTIVE | **Masked** | Sensor artifact; reflectance is not physical. |
| 2 | CAST_SHADOWS | Retained | Terrain shadow is a real observation of the surface under reduced illumination. Masking it would systematically delete hillsides and building shadows from every scene, biasing the sample. |
| 3 | CLOUD_SHADOWS | **Masked** | Cloud shadow darkens both bands unevenly and biases NDVI low; the surface is not properly observed. |
| 4 | VEGETATION | Retained | The signal of interest. |
| 5 | NOT_VEGETATED | Retained | Bare soil, built surfaces — legitimate low-NDVI observations needed for honest area statistics. |
| 6 | WATER | Retained | Water is a real surface with legitimately *negative* NDVI (NIR is strongly absorbed). Masking it would misrepresent AOIs containing lakes and rivers. |
| 7 | UNCLASSIFIED | Retained | The classifier abstained; the reflectance itself is not known to be contaminated. Excluding it would bias toward "easy" pixels. |
| 8 | CLOUD_MEDIUM_PROBABILITY | **Masked** | Probable cloud contamination of the red/NIR ratio. |
| 9 | CLOUD_HIGH_PROBABILITY | **Masked** | Cloud, not surface. |
| 10 | THIN_CIRRUS | **Masked** | Partially transparent cirrus skews the red/NIR ratio while looking superficially plausible. |
| 11 | SNOW_OR_ICE | **Masked** | NDVI over snow is not a vegetation signal; including it would produce spurious winter "vegetation loss". |

### 2.3 NDVI computation

`earth_observation/ndvi.py:compute_ndvi`:

- Math in **float64**; output stored as **float32**.
- `NDVI = (NIR − Red) / (NIR + Red)` on offset-corrected reflectance.
- **Negative reflectance is clipped to zero** before the ratio. Negative
  surface reflectance is a retrieval artifact (common over water and deep
  shadow once the baseline-04.00 offset is removed); without clipping, a
  near-zero denominator produces physically meaningless NDVI values of
  arbitrary magnitude. With clipping, NDVI is guaranteed to lie in [−1, 1].
  This mattered in practice: an April 2024 scene over the demonstration
  region produced a mean "NDVI" of ~2.5 × 10⁸ before this rule was added.
- **NaN** at every pixel that is masked by the SCL policy, non-finite in
  either band, or has a zero denominator (both bands zero after clipping).
- Zero-denominator pixels are **counted separately** — they indicate
  degenerate reflectance, not clouds, and the count is reported.
- The result is clipped to the exact AOI polygon on the canonical grid (§2.4).
  NDVI values outside the AOI are NaN.
- The output COG stores nodata as −9999 (float32, deflate-compressed,
  validated with rio-cogeo).

### 2.4 Canonical analysis grid (spatial comparability)

Every analysis derives **one** analytical grid from its AOI, and every
observation is reprojected onto it (`earth_observation/grid.py`):

| Property | Value |
|---|---|
| CRS | WGS84 UTM zone of the AOI centroid (native CRS of Sentinel-2 assets) |
| Resolution | 10 m (native GSD of B04/B08), configurable |
| Bounds | projected AOI bounds snapped **outward** to the resolution lattice anchored at the CRS origin |
| AOI mask | the AOI polygon rasterized on that grid — the analytical footprint |

Because the grid is fixed before any imagery is read, **every usable
observation shares an identical CRS, transform, width, height, bounds, and AOI
mask**. Cloud masking changes which pixels are valid; it can never change the
geographic region a date is measured over. The worker refuses to publish an
analysis whose observations disagree on their grid.

Snapping to the CRS origin (rather than to the AOI corner) means two analyses
over overlapping areas produce co-registered pixels.

### 2.5 Acquisition grouping and mosaicking

One Sentinel-2 acquisition is distributed as **one STAC item per MGRS tile**.
An AOI straddling a tile boundary therefore matches several items representing
the *same* observation instant — Detroit Urban Core matches T17TLG (100 % of
the AOI) and T17TLH (56 %).

Granules are grouped into acquisitions by observation time (rounded to the
minute), platform, relative orbit, and collection
(`earth_observation/acquisition.py`). The tile id and the *processing*
timestamp are deliberately excluded: granules of one acquisition are routinely
processed at different times, so keying on that would split them.

For each acquisition, every intersecting granule is read over its window only
and reprojected onto the canonical grid:

| Data | Resampling | Rationale |
|---|---|---|
| Red, NIR (continuous reflectance) | **bilinear** | Avoids aliasing when source and canonical grids are offset. Applied to both bands identically and *before* the ratio, so NDVI is not systematically biased. Cubic was rejected: its overshoot can push reflectance outside the physical range at water/land edges. |
| Scene Classification Layer (categorical) | **nearest** | Mandatory. Averaging class labels would invent classes that do not exist — interpolating cloud (9) and vegetation (4) would yield water (6). |
| True-color composite (visual only) | bilinear | Preview product, not analytical. |

Overlapping pixels resolve **first-valid-by-item-id**. Within one acquisition
the overlap observes the same ground at the same instant, so any consistent
rule is scientifically equivalent; determinism is what matters, and every
contributing item id is recorded in provenance.

### 2.6 Coverage validation

Geometric AOI coverage is computed for every acquisition. Acquisitions below
`min_aoi_coverage_pct` (default **99 %**) are marked unusable with reason
`insufficient_aoi_coverage` and excluded from the time series.

The coverage check runs **before** any cloud statistics: a partially observed
date is not comparable to a fully observed one regardless of how clean its
pixels are. Prior to version 2.0.0 this gate did not exist, and a granule
covering 56 % of an AOI could stand in for a whole observation
([ADR 0007](adr/0007-canonical-analysis-grid.md)).

Every AOI pixel is classified exactly once, in this precedence order (a pixel
cannot be "cloudy" over ground the sensor never saw):

1. **uncovered** — no source granule reached this pixel
2. **nodata** — covered, but the source carried no value
3. **cloud / shadow / cirrus** — masked by SCL policy
4. **snow / ice** — masked by SCL policy
5. **other masked** — saturated or defective
6. **invalid spectral** — non-finite reflectance or zero NDVI denominator
7. **valid** — contributes to statistics

These counts are reported per observation via the API and provenance, so a low
valid-pixel percentage can always be attributed to a specific cause.

### 2.7 Catalog search over long date ranges

A single STAC query returns at most ``max_items`` items in catalog order, so
querying a multi-year range in one call silently covers only part of it. In
practice, asking for 2018–2026 over Detroit returned granules from **2022
onward only** — an analysis that looked like eight years but was four.

Long ranges are therefore searched in consecutive windows of at most
``search_window_days`` (default 370), with the item cap applied **per window**
(``max_items_per_window``, default 150). Every period is queried, and total
candidates scale with the requested span rather than starving the early years.
With windowing, the same 2018–2026 request returns 345 granules spanning
2018-01-05 to 2026-06-27.

Any window that returns exactly its cap is recorded in provenance under
``catalog_search.truncated_windows`` and raised as an analysis warning: the
candidate set for that period is incomplete, so selection saw only part of
what exists.

### 2.8 Acquisition selection algorithms (deterministic)

Two strategies are available, and the choice materially changes what the
resulting time series means.

#### Temporal (`temporal-stratified-lowest-cloud` v2.0.0)

Spreads observations evenly across the requested range. Appropriate for
watching a **single growing season**. Selection operates on **acquisitions**,
not individual STAC items — selecting items directly is what previously
allowed a single partial granule to represent an observation. Given the
chronologically sorted acquisitions:

1. **Exclude** acquisitions whose granules together cover less than
   `min_aoi_coverage_pct` of the AOI. Reason: `insufficient_aoi_coverage`.
2. **Exclude** acquisitions above the requested cloud-cover threshold. Reason:
   `cloud_cover_above_threshold`. (Cloud cover is the coverage-weighted mean
   across contributing granules.)
3. If the survivors fit within the scene limit, **select them all**
   (chronological order).
4. Otherwise, split the requested date range into `scene_limit` **equal time
   buckets**. Within each non-empty bucket select the acquisition with the
   lowest sort key `(cloud_cover, observed_at, acquisition_key)`.
5. If some buckets were empty, **fill remaining slots** with the lowest-key
   unselected survivors, in the same deterministic order.
6. Every survivor not selected is recorded with reason
   `not_selected_temporal_sampling`.

The tuple sort key makes the algorithm fully deterministic: identical inputs
always produce identical selections.

#### Seasonal (`seasonal-same-window-lowest-cloud` v1.0.0)

Takes **one observation per year from the same part of the calendar**. This is
the only sound way to compare across years.

Why: in a temperate region NDVI swings from ~0.15 (dormant) to ~0.85 (peak
canopy) within a single year, while a multi-year trend is on the order of
0.02–0.05. Spreading eight scenes evenly over eight years picks arbitrary
months — a real run chose June, February, April, May, April, October, June,
May — so the resulting "trend" is dominated by which month each scene happened
to fall in, by roughly an order of magnitude.

1. Apply the coverage and cloud gates exactly as above.
2. Exclude acquisitions further than `seasonal_tolerance_days` (default 30)
   from the target day-of-year, recorded as `outside_seasonal_window`. The
   distance wraps around the year boundary and uses the observation year's
   actual length, so a leap year does not shift the window by a day.
3. Group survivors by calendar year; per year take the lowest
   `(cloud_cover, |day offset from target|, acquisition_key)`. Cloud leads
   because cloud contamination is the larger threat to the measurement;
   proximity to the target date breaks ties.
4. If more years survive than the scene limit, keep an evenly spaced subset
   that always includes the **first and last** year, so the series still spans
   the whole period (`not_selected_year_sampling`).

A year with nothing usable is simply **absent** from the series — a gap, not a
substitute from the wrong season. The target month and tolerance are recorded
in provenance under `scene_selection.seasonal_target`.

Both algorithms record every exclusion with its reason in the analysis
provenance ([ADR 0003](adr/0003-scene-selection-strategy.md),
[ADR 0007](adr/0007-canonical-analysis-grid.md)).

> **Interpreting a multi-year series.** Even with seasonal anchoring, a small
> difference between years is not automatically a trend. An 8-year run over
> Detroit produced early-July means between 0.346 and 0.393 with a first-to-last
> change of +0.017 — smaller than the year-to-year variation in the same
> series, so it does not establish a direction of change. The platform reports
> the observations; it does not perform trend or significance testing.

### 2.9 Per-observation statistics

All statistics are computed **over valid pixels only** — pixels inside the
**canonical AOI mask** that survived masking and had a computable NDVI
(`earth_observation/stats.py`). Because the mask comes from the canonical grid
rather than from each scene's own footprint, every observation is measured over
exactly the same ground:

- `ndvi_min`, `ndvi_max`, `ndvi_mean`, `ndvi_median`, `ndvi_std`
- Percentiles: `ndvi_p10`, `ndvi_p25`, `ndvi_p75`, `ndvi_p90`
- Counts: `valid_pixel_count`, `masked_pixel_count`, `aoi_pixel_count`,
  `zero_denominator_pixel_count`, and `valid_pixel_pct`

Scenes with **fewer than 10% valid pixels** are recorded (with full counts)
but **excluded from the time series** — reason `insufficient_valid_pixels`,
or `all_pixels_masked` when nothing survived. A mean over a sliver of
cloud-free pixels is not comparable to a mean over the whole AOI, so such
scenes would contaminate the series.

The time-series CSV contains **actual observation dates only**. Missing dates
are never interpolated; gaps are visible as gaps.

### 2.10 Display range vs analytical range

Colorized NDVI previews use a fixed display range of **−0.2 to 0.9** with a
brown → yellow → green ramp and transparency where masked. This range is a
*rendering* choice for visual comparability across scenes. It never clips
analytical values: the float32 COG and all statistics retain the full
computed range, including NDVI below −0.2 (e.g., water) and above 0.9.

---

## 3. Interpretation

NDVI is a normalized index in [−1, 1] contrasting near-infrared reflectance
(high for healthy mesophyll tissue) with red reflectance (absorbed by
chlorophyll). Approximate interpretation ranges for mid-latitude summer
scenes:

| NDVI | Typical surface |
| --- | --- |
| < 0 | Water, some snow/cloud residue |
| 0.0 – 0.1 | Bare soil, rock, built surfaces |
| 0.1 – 0.3 | Sparse or stressed vegetation, senescent grass |
| 0.3 – 0.6 | Moderate vegetation: crops, shrubs, lawns |
| 0.6 – 0.9 | Dense, healthy vegetation: forest canopy, vigorous crops |

These are conventions, not thresholds with physical guarantees. Comparisons
are most meaningful *within the same AOI across time* using the same mask
policy — which is exactly what the platform holds constant. An increase in
mean NDVI across a growing season indicates green-up; a persistent decline
across comparable dates in successive years indicates *something* changed and
warrants investigation, not a conclusion. See
[limitations.md](limitations.md) before attributing causes.

---

## 4. Uncertainty sources

In rough order of impact for this platform's use case:

1. **SCL misclassification.** The scene classifier makes mistakes: haze and
   bright surfaces are confused, cloud edges leak through, shadows are
   under-detected. Masked-class choice bounds but does not eliminate
   contamination.
2. **Undetected thin cirrus.** Sub-visible cirrus depresses NIR more than
   red, biasing NDVI low without triggering SCL class 10.
3. **BRDF and sun-angle effects.** Reflectance depends on sun and view
   geometry. Scenes months apart differ in solar elevation; part of any NDVI
   difference is geometry, not vegetation. No BRDF normalization is applied.
4. **Processing-baseline changes.** The offset is handled (section 2.1), but
   ESA also revises the atmospheric correction itself between baselines,
   introducing small discontinuities.
5. **Revisit gaps and temporal sampling.** Sentinel-2 revisits roughly every
   5 days, but cloudy scenes are excluded, so the *observed* series is
   irregular — and biased toward clear weather (see
   [limitations.md](limitations.md)).
6. **Geometric registration.** Sub-pixel misregistration between dates adds
   noise at field boundaries and in heterogeneous urban areas.

---

## 5. Limitations

Documented separately and prominently in [limitations.md](limitations.md).
The most important one repeats here: **an NDVI change is an observed
spectral change, not a diagnosis.** The platform's own analysis summary
embeds this note in every output.
