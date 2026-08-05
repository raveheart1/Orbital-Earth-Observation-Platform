# Security

Security posture of the Orbital Earth Observation Platform: what is
protected, how, and which limitations are consciously accepted at MVP stage.
Vulnerability reporting is described in the repository-level
[SECURITY.md](../SECURITY.md).

Related: [architecture.md](architecture.md),
[deployment.md](deployment.md), [operations.md](operations.md).

## Threat model summary

The platform is a **public demonstration** that processes only public
satellite data. There are no user accounts and no private user data beyond
submitted AOI geometries. The assets worth protecting are:

| Asset | Threats considered |
| --- | --- |
| Azure subscription / credentials | Credential theft from CI, leaked secrets in code or logs |
| Compute and storage spend | Abuse of the public submission endpoint (resource exhaustion, cost inflation) |
| Database | Injection via user-supplied geometry/parameters, direct network access |
| Blob artifacts | Enumeration/scraping of private artifacts, permanent public links |
| Service integrity | Malformed input crashing workers, poisoned queue messages, dependency compromise |
| Operational data | Sensitive detail leaking through error messages or logs |

Out of scope at this stage: authenticated multi-tenancy, DDoS resistance
beyond platform defaults, and formal compliance regimes.

## Controls

### Identity: no client secrets anywhere

- **GitHub Actions → Azure** uses **OIDC federation** — short-lived tokens
  scoped to the repository and the `dev` environment. There are no
  deployment client secrets to steal, rotate, or accidentally commit
  ([ADR 0005](adr/0005-managed-identity-oidc.md)).
- **Workloads → Azure resources** use a **user-assigned managed identity**
  for Storage (blobs, queues) and Key Vault. Application configuration
  contains no storage keys.
- The bootstrap script (`scripts/bootstrap-azure-github.sh`) refuses to run
  against subscriptions with "prod" in the name — a deliberate guard against
  pointing a demo pipeline at production.

### Storage

- Blob containers are **private**. Downloads go through the API, which issues
  **short-lived SAS URLs** (15 minutes by default) — user-delegation SAS in
  Azure (derived from the managed identity, no account keys), account-key SAS
  only against the local Azurite emulator.
- Artifact paths are namespaced per analysis (`analyses/{analysis_id}/...`)
  with UUIDv4 ids, and a 30-day lifecycle policy deletes old artifacts.

### Network and platform

- PostgreSQL Flexible Server is private; only the Container Apps environment
  reaches it. Credentials live in **Key Vault**, resolved via managed
  identity.
- Containers run as **non-root** users.
- Dependencies are **pinned** via `uv.lock` (Python) and `pnpm-lock.yaml`
  (web); the lockfile's sha256 is recorded in every provenance document, so
  the exact dependency set of any result is auditable.

### API hardening

- **Validation first:** AOI geometry is strictly validated (geodesic area
  limits, antimeridian and malformed boxes rejected) before any remote call.
  Dates, cloud thresholds, and scene limits are bounded server-side
  (`OEOP_*` settings), regardless of what the UI sends.
- **Rate limiting:** 10 submissions/hour/client (best-effort, per replica —
  see limitations below).
- **Request caps:** maximum body size 64 KB.
- **Headers and CORS:** restrictive CORS (the browser talks to the Next.js
  proxy, not the API) and standard security headers.
- **Custom-area cap:** visitor-drawn areas of interest are accepted
  (`OEOP_ALLOW_CUSTOM_AREAS`, default on) but capped at
  `OEOP_MAX_CUSTOM_AOI_AREA_KM2` (default **2 km²**) — two orders of magnitude
  below the limit applied to the curated predefined regions. The cap is
  enforced server-side in `create_analysis`, not merely in the browser, so a
  hand-crafted request cannot obtain a large arbitrary AOI. Combined with the
  submission throttle and scene limits, this bounds what an anonymous caller
  can make the platform spend.
- **No synthetic data in deployed environments.** Synthetic satellite rasters
  exist only for automated tests. `earth_observation.testing` (the generator)
  is excluded from the built wheel, so container images — which install that
  wheel via `uv sync --no-editable` — do not contain it; tests import it from
  source through the editable dev install and are unaffected. The committed
  demonstration bundle under `data/` is likewise never copied into an image:
  deployed environments run `seed-demo`, which processes live Sentinel-2
  imagery. Three layers enforce this: the wheel exclusion, the tests in
  `tests/test_no_synthetic_data_in_production.py` (which build the wheel and
  inspect it), and a CI step that greps the built images.
- **Kill switches:** `DEMO_MODE` restricts submissions to predefined regions
  with tighter limits; `OEOP_SUBMISSIONS_ENABLED=false` disables public
  submissions entirely ([runbook](operations.md#disable-public-submissions)).

### Errors and logs

- Errors are returned as RFC 7807 `application/problem+json`
  ([api-errors.md](api-errors.md)). Internal exception details never reach
  clients: unexpected errors return an opaque correlation id, and the detail
  is logged server-side against that id.
- Logs are structured JSON (structlog) and avoid secrets by construction;
  signed URLs are never logged or persisted (see
  [data-provenance.md](data-provenance.md#unsigned-vs-signed-url-policy)).

### Processing integrity

- The worker treats queue messages as untrusted: the message carries only an
  `analysis_id`; all configuration is loaded from the database.
- Malformed or repeatedly failing messages go to a **poison queue** after 3
  deliveries instead of looping.
- The failure taxonomy ensures user-triggerable errors (`user_input`,
  `data`) are never retried, so a crafted request cannot induce retry storms.

## Known MVP limitations (accepted, documented)

| Limitation | Consequence | Mitigation in place |
| --- | --- | --- |
| Rate limiter is per-replica and in-memory | Effective limit scales with replica count; restarts reset counters | Replica counts are small; body-size caps, scene limits, and job runtime caps bound worst-case cost per request |
| No authentication on public demo endpoints | Anyone can submit analyses and read demo results | DEMO_MODE region restriction, tight quotas, `submissions_enabled` kill switch, 30-day retention, private blobs with short-lived SAS |
| No WAF / DDoS protection beyond Azure platform defaults | Volumetric abuse could exhaust rate limits or spend | Scale-to-zero caps idle cost; kill switch stops intake |
| Abuse controls are reactive | Sustained low-and-slow abuse is possible until noticed | Structured logs + Log Analytics queries by client, documented shutdown procedures |

These are conscious trade-offs for a portfolio/demo system, not oversights;
adding an auth layer in front of submissions is the first step if the
platform ever hosts non-demo workloads.

## Secret rotation guidance

The design minimizes rotatable secrets; what remains:

| Secret | Where | Rotation |
| --- | --- | --- |
| PostgreSQL password | Key Vault | Rotate via Key Vault + `terraform apply`; step-by-step in [operations.md](operations.md#rotate-the-postgresql-password) |
| OIDC federation | Azure AD app federated credentials | Nothing to rotate (no secret material); review federated subjects when repo/environment names change |
| Managed identity | Azure-managed | Nothing to rotate |
| Azurite well-known key (local only) | docker-compose | Public emulator constant; never used in Azure |

If any credential is suspected compromised: disable submissions, rotate the
PG password, and review Log Analytics access logs — in that order (see
[operations.md](operations.md)).
