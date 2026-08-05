# Limitations

Read this before interpreting any output of the platform. These limitations
are not fine print; they define what the numbers mean. The methodology behind
them is in [scientific-methodology.md](scientific-methodology.md).

## NDVI change is not a diagnosis

The platform reports **observed spectral changes for specific acquisition
dates**. By itself, an NDVI decline does **not** establish:

- **Drought.** Mowing, harvest, construction, phenology (normal seasonal
  senescence), and irrigation changes all lower NDVI.
- **Wildfire damage.** Burn scars lower NDVI, but so do clearing, plowing,
  and flooding. Attribution needs independent evidence (thermal anomalies,
  ground reports, burned-area products).
- **Climate change.** A trend across a handful of scenes in a two-year window
  is weather and land management, not climate. Climate attribution requires
  decades of data and careful methodology far beyond this platform.
- **Agricultural failure.** Crop rotation alone produces large year-over-year
  NDVI swings on the same field.

Every analysis summary embeds an interpretation note to this effect. Treat
platform output as a *screening instrument*: it tells you where and when to
look closer, not what happened.

## Cloud masking is imperfect

The SCL mask ([policy table](scientific-methodology.md#22-scl-mask-policy))
is a classifier output, not ground truth. Cloud edges, haze, and thin cirrus
leak through; bright roofs and sand are sometimes falsely masked as cloud.
Residual contamination usually biases NDVI **low**, so isolated dips in a
time series deserve suspicion before interpretation.

## Temporal sampling is biased toward clear weather

Two compounding selection effects:

1. The STAC query excludes scenes above the cloud-cover threshold.
2. The selection algorithm prefers the **lowest-cloud** scene in each time
   bucket.

The resulting series systematically over-samples clear, dry, often
high-pressure conditions. Vegetation state during prolonged overcast or wet
periods is under-observed. Gaps are honest — dates are never interpolated —
but the *sampled* dates are not a random draw of days.

## NDVI saturates over dense canopy

Above roughly 0.8, NDVI compresses: substantial differences in leaf area or
biomass in a closed forest canopy produce almost no NDVI difference. The
platform can therefore *understate* change in dense forest (e.g., Hartwick
Pines) while resolving it well in grass, crops, and open canopy.

## Mixed pixels at 10 m

Each pixel integrates a 10 m × 10 m footprint. Street trees + asphalt, field
edges, riparian strips, and residential lots are all spectral mixtures. Pixel
values in heterogeneous areas are area-weighted averages of dissimilar
surfaces, and small geolocation shifts between dates move those mixtures
around. Statistics over the whole AOI are robust to this; individual-pixel
comparisons are not.

## Urban NDVI needs extra care

Much of Southeast Michigan is urban or suburban. There:

- Mean NDVI is dominated by the *fraction* of vegetated surface, not
  vegetation *health*. A mowed lawn and a vacant lot differ more in NDVI than
  a healthy and a mildly stressed lawn.
- Shadows from buildings vary with sun angle across the year, adding a
  seasonal signal unrelated to vegetation (cast shadows are retained by the
  mask policy, deliberately — see the
  [rationale](scientific-methodology.md#22-scl-mask-policy)).
- Impervious-surface changes (construction, paving) produce sharp permanent
  NDVI drops that are real land-cover change, not vegetation stress.

## Scale and scope of the demo

- Visitor-drawn areas are capped at 2 km² (`OEOP_MAX_CUSTOM_AOI_AREA_KM2`).
  Larger areas are available through the curated predefined regions, which are
  capped at 600 km² (250 km² in demo mode), with at most 12 scenes
  per analysis (default 6, demo 8). This is a demonstration-scale window, not
  a monitoring system: statements about "Southeast Michigan" from one AOI and
  a dozen dates are anecdotes, not surveys.
- Date ranges are capped (730 days; earliest start 2016-01-01), so
  long-horizon trends are out of scope.
- Scenes with under 10% valid pixels are excluded from the series
  (recorded with reasons), which further thins winter and cloudy-season
  coverage.
- Artifacts are retained for 30 days in the deployed dev environment;
  provenance documents make results reproducible after deletion (see
  [data-provenance.md](data-provenance.md)).

## Comparing observations across dates

Since processing version 2.0.0 every observation in an analysis is computed on
one canonical grid over an identical AOI footprint, so a change between two
dates reflects the surface, not a change of measurement area.

Two caveats remain:

* **Results from processing version 1.x are not comparable across dates when
  the AOI crossed a Sentinel-2 tile boundary.** In that version a single
  granule could represent an observation while covering only part of the AOI.
  Such analyses report `grid: null` via the API and are labelled accordingly in
  the interface. Re-run them to obtain comparable results.
* Acquisitions that do not cover at least 99% of the AOI are excluded
  entirely. This is deliberate — but it means a cloudy or edge-of-swath period
  may yield fewer observations than the requested scene limit, and the
  remaining dates are not a random sample of the period.

## Known technical caveats

- No BRDF/sun-angle normalization is applied; cross-season comparisons carry
  a geometry component ([uncertainty sources](scientific-methodology.md#4-uncertainty-sources)).
- Processing-baseline offsets are corrected, but ESA's atmospheric-correction
  revisions between baselines can introduce small discontinuities.
- The 20 m SCL is applied to 10 m pixels (nearest-neighbor), so mask edges
  are blocky at 2×2-pixel granularity.
