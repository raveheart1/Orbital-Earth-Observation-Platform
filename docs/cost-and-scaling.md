# Cost and scaling

A qualitative account of what the dev deployment costs, what drives those
costs, and how the system behaves as usage grows. No prices are quoted here —
Azure pricing varies by region and changes over time; the *structure* of the
costs is what matters and is stable.

Related: [architecture.md](architecture.md),
[operations.md](operations.md#destroy-the-dev-environment-safely),
[deployment.md](deployment.md).

## What dominates the bill

In rough descending order for a lightly used dev environment:

1. **PostgreSQL Flexible Server (B1ms).** The one always-on component, and
   therefore the main baseline cost. It bills whether or not anyone runs an
   analysis. Everything else in the system can scale to zero; the database
   cannot (short of stopping it — see below).
2. **Log Analytics ingestion.** Billed per GB ingested. Structured JSON
   logging is verbose by design; log volume scales with analyses processed
   and with chattiness of debug settings. This is the cost most likely to
   surprise, and the one most directly controlled by log-level discipline.
3. **Container Apps (consumption).** API, web, and worker bill for vCPU and
   memory while running. The worker is a KEDA-scaled job that **scales to
   zero** between analyses; API and web are small and mostly idle in a demo.
   Compute cost scales nearly linearly with analyses processed, since worker
   runtime is the bulk of it.
4. **Blob storage.** Artifacts are small (windowed NDVI COGs and PNGs for
   ≤600 km² AOIs), capped at 200 MB per analysis, and deleted by a 30-day
   lifecycle policy, so storage cost stays bounded rather than growing
   without limit.
5. **ACR (Basic)** — flat and small.
6. **Egress** — minimal by design: the worker performs windowed range reads
   of only the AOI, never full-scene downloads, and reads *from* the
   Planetary Computer are ingress from the worker's perspective. User-facing
   egress is small PNGs, CSVs, and JSON.

## How usage scales cost

| Usage change | Cost effect |
| --- | --- |
| More analyses per day | Worker compute and Log Analytics ingestion scale roughly linearly; blob storage plateaus because of 30-day retention. |
| Larger AOIs (up to the 600 km² cap) | More pixels per scene → longer worker runs and larger COGs. Bounded by the per-analysis storage cap (200 MB) and job runtime cap (1500 s). |
| Visitor-drawn AOIs | Capped at 250 km² by default. The number comes from measured output volume — about **0.06 MB per scene per km²** — against the 200 MB per-analysis storage cap: storage binds near **417 km² at 8 scenes** (278 km² at 12), so 250 km² keeps a margin below both. Runtime is not the constraint: a 137 km² region takes ~10–12 s per scene, so even a full 12-scene run finishes well inside the 1500 s job cap. Small boxes remain very cheap (a 0.9 km² area yields a ~95 × 101 pixel grid and completes in seconds), and the cap still bounds the worst case an anonymous caller can request. |
| More scenes per analysis (up to 12) | Linear in worker time and artifacts. |
| Zero usage | Cost collapses to the Flexible Server, Log Analytics baseline, and ACR. |

The request-side limits ([architecture.md](architecture.md#configuration))
double as cost controls: every knob that bounds science also bounds spend.

## Scale-to-zero and cold starts

The worker runs as a Container Apps Job with KEDA queue-length scaling and a
floor of zero replicas. When the queue is empty, no worker compute bills.
The trade-off is **cold start**: the first analysis after an idle period
waits for image pull and container start before processing begins. For an
asynchronous pipeline whose users already expect minutes-scale turnaround,
this is accepted deliberately — the alternative (a warm worker) would make
the worker, not the database, the dominant cost.

The API and web apps use consumption-plan Container Apps and can also scale
to minimal replicas; their cold starts affect interactive latency, which
matters more, so their minimum replica settings are the first thing to raise
if the demo needs to feel snappy.

## Retention settings

- Blob artifacts: 30-day lifecycle deletion (configurable). Provenance makes
  results reproducible after deletion, so retention is a cost knob, not a
  data-loss risk ([data-provenance.md](data-provenance.md)).
- Log Analytics retention: keep at the default; longer retention multiplies
  the second-largest cost for little demo value.
- Database rows (analyses, scenes, observations) are small and kept; they
  are the cheap, durable record.

## Region trade-off: eastus vs westeurope

Planetary Computer Sentinel-2 data is hosted in **West Europe**. The deploy
default is **eastus**, which means every asset read crosses the Atlantic:

- **eastus (default):** lower latency for US-based users of the web UI;
  higher latency (and somewhat longer worker runtimes) for PC asset reads.
- **westeurope:** worker-to-data reads become intra-region — faster scene
  processing and the least data movement — at the cost of higher UI latency
  for US users.

For a US-audience demo the default favors the interactive path and accepts
slower background processing. A batch-heavy deployment should choose
westeurope. Either way, egress cost impact is small because only AOI windows
are read.

## Shutting down

Cheapest-first options when the environment is not needed:

1. **Do nothing.** Worker is already at zero between analyses; idle cost is
   the Flexible Server + Log Analytics baseline.
2. **Disable submissions** (`OEOP_SUBMISSIONS_ENABLED=false`) to stop new
   spend from public use while keeping reads available
   ([operations.md](operations.md#disable-public-submissions)).
3. **Stop the Flexible Server** (`az postgres flexible-server stop`).
   Removes the dominant cost — but Azure automatically **restarts a stopped
   Flexible Server after 7 days**; this is a pause, not a shutdown.
4. **Destroy the environment** via the `destroy-dev` workflow (typed
   confirmation required). Terraform state and the bootstrap setup make
   re-creation reproducible, so destroying dev is cheap insurance for long
   idle periods ([operations.md](operations.md#destroy-the-dev-environment-safely)).
