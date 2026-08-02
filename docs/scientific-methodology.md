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
cloud-optimized GeoTIFFs); full scenes are never downloaded. The 20 m SCL is
aligned to the 10 m band grid with **nearest-neighbor** resampling — SCL
values are class labels, and any interpolating resampler would invent
meaningless intermediate classes.

Processing happens in each scene's **native UTM CRS**: the AOI polygon is
transformed into the scene CRS and rasters are clipped exactly to it, with no
reprojection of the measurement grid ([ADR 0004](adr/0004-native-utm-processing.md)).

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
- The result is clipped to the exact AOI polygon in the scene's native UTM
  grid. NDVI values outside the AOI are NaN.
- The output COG stores nodata as −9999 (float32, deflate-compressed,
  validated with rio-cogeo).

### 2.4 Scene selection algorithm (deterministic)

Algorithm `temporal-stratified-lowest-cloud`, version `1.0.0`
(`earth_observation/selection.py`). Given the chronologically sorted STAC
candidates (at most 200 fetched, each annotated with its AOI overlap
percent):

1. **Exclude** candidates whose footprint covers less than 25% of the AOI
   (configurable `min_aoi_overlap_pct`). Recorded reason:
   `insufficient_aoi_overlap`.
2. **Exclude** candidates above the requested cloud-cover threshold
   (defensive; the STAC query already filters `eo:cloud_cover <` threshold).
   Recorded reason: `cloud_cover_above_threshold`.
3. If the survivors fit within the scene limit, **select them all**
   (chronological order).
4. Otherwise, split the requested date range into `scene_limit` **equal time
   buckets**. Within each non-empty bucket select the candidate with the
   lowest sort key `(cloud_cover, observed_at, item_id)`.
5. If some buckets were empty, **fill remaining slots** with the lowest-key
   unselected survivors, in the same deterministic order.
6. Every survivor not selected is recorded with reason
   `not_selected_temporal_sampling`.

The tuple sort key makes the algorithm fully deterministic: identical inputs
always produce identical selections, and ties (equal cloud cover, equal
timestamp) break on `item_id`. Every exclusion is recorded with its reason in
the analysis provenance ([ADR 0003](adr/0003-scene-selection-strategy.md)).

### 2.5 Per-scene statistics

All statistics are computed **over valid pixels only** — pixels inside the
AOI that survived masking and had a computable NDVI
(`earth_observation/stats.py`):

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

### 2.6 Display range vs analytical range

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
