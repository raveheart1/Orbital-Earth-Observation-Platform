# ADR 0003: Deterministic temporal-stratified scene selection

Status: accepted

## Context

A date range can match far more scenes than the per-analysis scene limit
(≤12). Some subset must be chosen. Naive strategies fail differently:
"lowest cloud overall" clusters observations in one clear month and destroys
temporal coverage; "first N" ignores quality; anything nondeterministic
makes results irreproducible and exclusions unexplainable.

## Decision

Algorithm `temporal-stratified-lowest-cloud` v1.0.0
(`earth_observation/selection.py`): filter by AOI overlap (≥25%) and cloud
threshold; if survivors exceed the limit, split the date range into
`scene_limit` equal time buckets and pick per bucket by the total order
`(cloud_cover, observed_at, item_id)`; fill empty-bucket slots from
lowest-key leftovers. Every excluded candidate is recorded with a reason
(`insufficient_aoi_overlap`, `cloud_cover_above_threshold`,
`not_selected_temporal_sampling`). The algorithm name and version are stored
in provenance, so future strategy changes version explicitly rather than
silently altering results.

## Consequences

- Identical inputs always yield identical selections; reproduction and
  testing are exact ([data-provenance.md](../data-provenance.md#reproducing-a-result-from-a-provenance-document)).
- "Why isn't scene X included?" is answerable from the provenance document.
- The lowest-cloud preference biases the series toward clear weather — a
  documented limitation ([limitations.md](../limitations.md#temporal-sampling-is-biased-toward-clear-weather)).
- Equal-width time buckets can sit awkwardly against irregular revisit
  patterns; a future version could stratify by orbit cycle instead.
