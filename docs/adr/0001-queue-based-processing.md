# ADR 0001: Queue-based asynchronous processing

Status: accepted

## Context

An NDVI analysis takes minutes: STAC search, several windowed COG reads per
scene, raster math, artifact uploads. HTTP request/response cannot host that
work — timeouts, no retry story, and the API would need worker-sized
compute. We also want processing capacity to cost nothing when idle.

## Decision

Submissions are asynchronous. The API validates, persists an `Analysis` row,
and enqueues `{analysis_id}` on an Azure Storage Queue **after** the database
commit. A KEDA-scaled Container Apps Job consumes the queue and scales to
zero when it is empty. Reliability semantics (at-least-once delivery made
effectively exactly-once) come from: atomic claim via conditional UPDATE
(queued→running), stale-lease reclaim after 2 h, idempotent reprocessing
that deletes partial outputs, visibility renewal during long runs, a poison
queue after 3 deliveries, and message deletion only after durable
completion. Azure Storage Queue was chosen over Service Bus because its
semantics (visibility timeout, dequeue count) are sufficient and it is the
cheapest, simplest option already bundled with the storage account.

## Consequences

- Users poll (`202` + `Location`); the UI must present in-progress state.
- Worst-case duplicate delivery is handled by design rather than assumed
  away; every reliability mechanism is testable in isolation.
- Scale-to-zero makes cold starts part of the normal experience
  ([cost-and-scaling.md](../cost-and-scaling.md#scale-to-zero-and-cold-starts)).
- Operational surface grows: queue depth, poison queue, and requeue tooling
  become runbook items ([operations.md](../operations.md)).
