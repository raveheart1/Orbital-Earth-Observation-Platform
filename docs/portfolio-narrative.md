# Portfolio narrative

*A one-page account of what this project demonstrates, for anyone evaluating
it as a body of work.*

## The question, and why it is a good one

"How has vegetation health changed across selected areas of Southeast
Michigan over time, based on Sentinel-2 satellite observations?" — a real
scientific question, small enough to answer honestly, large enough to
require genuine engineering. Answering it well forces three disciplines to
meet: **scientific correctness** (the number must be right),
**cloud engineering** (the system must be reliable and cheap), and
**reproducibility** (the number must be checkable by someone else).

## What it demonstrates

**Scientific correctness.** The pipeline handles the details that separate a
demo from a defensible measurement: the Sentinel-2 processing-baseline
additive offset that does *not* cancel in the NDVI ratio; a per-class SCL
mask policy with written rationale for retained classes (water's legitimately
negative NDVI, terrain shadows as real observations); nearest-neighbor
alignment of the 20 m classification layer so class labels are never
interpolated; float64 math with explicit zero-denominator accounting;
statistics over valid pixels only, with sub-10%-valid scenes excluded rather
than quietly averaged; and observation dates never interpolated. Every one of
these is documented ([scientific-methodology.md](scientific-methodology.md))
and matched by honest limitations ([limitations.md](limitations.md)) — the
platform explicitly refuses to claim NDVI change proves drought or climate
trends.

**Cloud engineering.** Queue-decoupled processing with exactly-once
*effects* on at-least-once delivery: enqueue-after-commit, atomic claims,
stale-lease reclaim, idempotent reprocessing, visibility renewal, poison
queues, and a failure taxonomy that retries only what retrying can fix
([architecture.md](architecture.md#reliability-design)). Zero client
secrets: GitHub OIDC for deploys, managed identity for workloads,
user-delegation SAS for downloads. Scale-to-zero workers keep idle cost at
one small database.

**Reproducibility.** Every analysis ships a schema-validated provenance
document: catalog items, unsigned asset hrefs, full config snapshot, mask
policy, selection algorithm version with every exclusion and its reason, git
SHA, container image, lockfile hash, and per-artifact sha256
([data-provenance.md](data-provenance.md)). Scene selection is fully
deterministic. A notebook imports the same science package as production and
reproduces a scene end to end.

## The hard parts

1. **The baseline offset.** The obvious NDVI implementation is subtly wrong
   for post-2022 scenes, in a way that manufactures fake vegetation change
   exactly where the platform claims to measure real change. Getting this
   right required reading ESA processing-baseline documentation, a
   priority-ordered scaling resolution (STAC `raster:bands` metadata over
   baseline heuristic over default), and recording the decision per scene.
2. **Deterministic selection.** Designing a scene-selection algorithm that
   is quality-aware, temporally stratified, *and* a pure function of its
   inputs — with every exclusion recorded — so results are explainable and
   reproducible ([ADR 0003](adr/0003-scene-selection-strategy.md)).
3. **Idempotent queue processing.** Making duplicate delivery, worker
   crashes, and partial output all converge to a single correct result
   without a workflow engine ([ADR 0001](adr/0001-queue-based-processing.md)).
4. **OIDC end to end.** A deploy pipeline and runtime with no client secret
   anywhere, including the bootstrap chicken-and-egg and a two-stage
   Terraform apply around image builds
   ([deployment.md](deployment.md)).

## What I would do next

- **Comparisons that mean more:** same-season year-over-year composites and
  per-pixel change maps with an explicit resampling ADR, reducing the
  phenology confound.
- **Better sampling honesty:** report cloud-forced observation gaps as
  first-class output, and stratify selection by orbit cycle rather than
  equal time buckets.
- **Auth in front of submissions** and a shared rate limiter, the two
  documented MVP security gaps ([security.md](security.md)).
- **A second index (e.g., NDWI)** to exercise the "operation" dimension the
  provenance schema already carries.
- **Westeurope deployment profile** for batch-heavy use, closing the data
  locality gap ([cost-and-scaling.md](cost-and-scaling.md)).
