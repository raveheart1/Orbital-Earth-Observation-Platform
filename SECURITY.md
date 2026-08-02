# Security policy

## Supported versions

Only the `main` branch is supported. There are no maintained release
branches; fixes land on `main` and deploy from there.

## Reporting a vulnerability

Please report vulnerabilities **privately** via GitHub Security Advisories:

1. Go to the repository's **Security** tab → **Report a vulnerability**.
2. Include reproduction steps, impact assessment, and affected paths.

Do **not** open a public issue or PR for security problems.

Response expectations for this single-maintainer project:

- Acknowledgment within **7 days**.
- Assessment and severity triage within **14 days** of acknowledgment.
- Fix or documented mitigation on `main` as soon as practical for confirmed
  issues; you will be credited in the advisory unless you prefer otherwise.

## Threat model and posture

The full threat model, controls (OIDC-only deployment, managed identity,
private blobs with short-lived SAS, validation and rate limits, sanitized
errors), and rationale live in [`docs/security.md`](docs/security.md).

### Known MVP limitations (documented, accepted)

These are known and deliberate at the current stage — reports that merely
restate them will be closed as known, though bypasses of their mitigations
are very much in scope:

- The submission rate limiter is **per-replica and in-memory** (best-effort).
- Public demo endpoints have **no authentication**; abuse controls are
  quotas, DEMO_MODE restrictions, and a submissions kill switch.
- No WAF/DDoS protection beyond Azure platform defaults.

## Secrets and rotation

The design goal is *no client secrets*: GitHub OIDC federation for
deployment, user-assigned managed identity for workloads. The remaining
rotatable secret is the PostgreSQL password (Key Vault); the rotation
procedure is in
[`docs/operations.md`](docs/operations.md#rotate-the-postgresql-password),
and the full secret inventory is in
[`docs/security.md`](docs/security.md#secret-rotation-guidance).

If you find credential material in the repository history or logs, treat it
as a vulnerability and report it privately as above.
