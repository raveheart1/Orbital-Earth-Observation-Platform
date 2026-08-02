# API errors

The API returns every error as an RFC 7807 problem-details document with
content type `application/problem+json`. Error `type` URIs link to the
anchor sections in this document. Implementation:
`apps/api/src/oeop_api/problem.py`.

Related: [architecture.md](architecture.md) for the endpoints,
[security.md](security.md#errors-and-logs) for why details are sanitized.

## Format

```json
{
  "type": "https://github.com/raveheart1/Orbital-Earth-Observation-Platform/blob/main/docs/api-errors.md#invalid-request",
  "title": "Invalid analysis request",
  "status": 422,
  "detail": "min_lon must be strictly less than max_lon (antimeridian-crossing boxes are not supported)",
  "instance": "/api/v1/analyses"
}
```

| Field | Meaning |
| --- | --- |
| `type` | URI identifying the error class; anchors below. `about:blank` for generic HTTP errors. |
| `title` | Short, stable, human-readable summary of the class. |
| `status` | The HTTP status code, repeated in the body. |
| `detail` | Human-readable explanation of this occurrence. Sanitized — never contains stack traces or internal state. |
| `instance` | The request path that produced the error. |
| `errors` | (Validation only) list of `{loc, message}` field errors. |

<a id="invalid-request"></a>
## Invalid request

- **Status:** `422 Unprocessable Entity`
- **Title:** `Invalid analysis request`

The request was understood but is semantically invalid: the analysis can
never succeed as specified, so it is rejected before any work is enqueued.
Typical causes:

- Malformed, empty, or self-intersecting AOI geometry
- Antimeridian-crossing bounding box (unsupported by design)
- AOI area outside limits (0.5–600 km²; 250 km² in demo mode)
- Date span too long (max 730 days; 400 in demo mode) or start before
  2016-01-01
- Scene limit or cloud threshold outside allowed bounds

Fix the request; retrying unchanged will always fail.

<a id="validation"></a>
## Request validation failed

- **Status:** `422 Unprocessable Entity`
- **Title:** `Request validation failed`

The request body or parameters do not match the API schema (missing fields,
wrong types). The `errors` array lists each offending field as
`{"loc": "body.start_date", "message": "..."}`. Distinct from
[invalid request](#invalid-request): validation errors are about *shape*,
invalid-request errors are about *meaning*.

<a id="data-error"></a>
## Data error

- **Status:** `409 Conflict`
- **Title:** `Upstream data cannot satisfy the request`

The request is valid, but the upstream catalog cannot fulfill it
deterministically: no scenes match the search, matching scenes lack required
assets (B04/B08/SCL), or all candidate scenes are excluded by selection or
masking. Retrying without changing the request will produce the same result
for the same catalog state. Widen the date range, raise the cloud threshold,
or adjust the AOI. See
[scientific-methodology.md](scientific-methodology.md#24-scene-selection-algorithm-deterministic)
for exclusion reasons.

<a id="internal"></a>
## Internal server error

- **Status:** `500 Internal Server Error`
- **Title:** `Internal server error`

An unexpected failure. The response deliberately contains no internal
detail — only a correlation id:

```
"detail": "An unexpected error occurred. Reference: 0b8f3c9e-..."
```

Operators can look up the full exception in the logs by that id
([operations.md](operations.md#view-logs)). Include the reference when
reporting.

## Common errors

| Status | Type anchor | When | Retry? |
| --- | --- | --- | --- |
| 422 | [#invalid-request](#invalid-request) | AOI/date/limit violations | After fixing the request |
| 422 | [#validation](#validation) | Schema violations (missing/wrong-typed fields) | After fixing the request |
| 409 | [#data-error](#data-error) | Catalog cannot satisfy the request | After changing parameters |
| 404 | `about:blank` | Unknown analysis/region id | No |
| 413 | `about:blank` | Body exceeds 64 KB | Reduce payload |
| 429 | `about:blank` | Rate limit exceeded (10 submissions/hour/client) | Wait and retry |
| 503 | `about:blank` | Submissions disabled (kill switch) or readiness failure | Later |
| 500 | [#internal](#internal) | Unexpected failure; correlation id in `detail` | Report with the reference id |

Note: an *accepted* analysis (`202`) that later fails during processing does
not surface here — its failure category and sanitized message appear on the
analysis resource (`GET /api/v1/analyses/{id}`); see
[operations.md](operations.md#find-a-failed-analysis).
