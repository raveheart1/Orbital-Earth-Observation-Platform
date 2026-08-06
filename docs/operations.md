# Operations runbook

Task-oriented procedures for running the platform in the Azure dev
environment and locally. Background: [architecture.md](architecture.md)
(lifecycle, reliability design), [deployment.md](deployment.md) (how the
environment is created), [security.md](security.md).

Conventions used below:

- `$RG` — the resource group (from `AZURE_RESOURCE_GROUP`).
- Resource names follow the Terraform config in `infra/`; substitute yours
  (discover with `az resource list -g $RG -o table`).
- Locally, run `oeop-admin` from the repo root as `uv run oeop-admin ...`.

## Find a failed analysis

Via API:

```bash
curl -s https://<api-host>/api/v1/analyses/<analysis_id> | jq
```

Status, failure category, and a sanitized message are on the analysis
resource. Related detail: `/scenes`, `/provenance` (if the run got far
enough), `/artifacts`.

Via SQL (psql against the Flexible Server, or the local `postgis`
container):

```sql
-- Recent failures with categories
SELECT id, status, failure_category, failure_message, created_at, updated_at
FROM analyses
WHERE status = 'failed'
ORDER BY updated_at DESC
LIMIT 20;

-- Stuck runs (candidates for stale-lease reclaim; lease is 2 hours)
SELECT id, status, updated_at
FROM analyses
WHERE status = 'running'
  AND updated_at < now() - interval '2 hours';

-- Per-scene outcomes for one analysis
SELECT item_id, usable, unusable_reason
FROM scenes
WHERE analysis_id = '<analysis_id>'
ORDER BY observed_at;
```

Failure categories and retry behavior (`user_input`, `data`, `transient`,
`timeout`, `internal`) are described in
[architecture.md](architecture.md#reliability-design). Transient failures
retry automatically via queue redelivery; deterministic ones do not.

## Inspect Container Apps Job executions

```bash
# List recent worker job executions and their status
az containerapp job execution list \
  -g $RG --name <worker-job-name> \
  --query "[].{name:name,status:properties.status,start:properties.startTime}" -o table

# Details of one execution
az containerapp job execution show \
  -g $RG --name <worker-job-name> --job-execution-name <execution-name>
```

## Requeue a failed or stuck analysis

```bash
uv run oeop-admin requeue --analysis-id <uuid>
```

This resets the row and enqueues a fresh message. Reprocessing is idempotent:
prior partial outputs are deleted before new ones are written, so requeueing
a half-finished analysis is always safe. Only requeue deterministic failures
after fixing the cause (they will fail identically otherwise).

## View logs

Live tail from a Container App:

```bash
az containerapp logs show -g $RG --name <api-app-name> --follow
az containerapp job logs show -g $RG --name <worker-job-name> \
  --execution <execution-name> --container worker
```

Log Analytics (KQL) — logs are structured JSON with `analysis_id` as a
field, so a whole run can be traced end to end:

```kusto
// Everything the worker logged for one analysis
ContainerAppConsoleLogs_CL
| where Log_s has "7f3d2c1a-9b4e-4f6a-8c2d-1e5f7a9b3c4d"
| extend entry = parse_json(Log_s)
| where tostring(entry.analysis_id) == "7f3d2c1a-9b4e-4f6a-8c2d-1e5f7a9b3c4d"
| project TimeGenerated, entry.level, entry.event, entry
| order by TimeGenerated asc
```

```kusto
// Error-level events across all apps, last 24 h
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(24h)
| extend entry = parse_json(Log_s)
| where tostring(entry.level) == "error"
| project TimeGenerated, ContainerAppName_s, entry.event,
          entry.analysis_id, entry.correlation_id
| order by TimeGenerated desc
```

```kusto
// Unhandled API exceptions by correlation id (matches the id returned to the client)
ContainerAppConsoleLogs_CL
| extend entry = parse_json(Log_s)
| where tostring(entry.event) == "unhandled_exception"
| project TimeGenerated, entry.correlation_id, entry.path
```

Application Insights holds request/dependency traces via OpenTelemetry;
correlate with the same analysis id.

## Check queue depth

```bash
# Through the platform (uses configured credentials)
uv run oeop-admin queue-depth

# Directly (Azure)
az storage queue stats --name <queue-name> \
  --account-name <storage-account> --auth-mode login \
  --query approximateMessageCount
```

Also check the poison queue — messages land there after 3 failed
deliveries; a non-empty poison queue always deserves investigation.

## Rotate the PostgreSQL password

1. Generate a new password and set it as the Key Vault secret value used by
   the Terraform config (or update the Terraform variable if managed there).
2. `terraform apply` in `infra/` (or re-run the deploy workflow) so the
   Flexible Server administrator password and the Key Vault secret move
   together.
3. Restart API and worker so they pick up the new secret:
   ```bash
   az containerapp revision restart -g $RG --name <api-app-name> \
     --revision $(az containerapp show -g $RG --name <api-app-name> \
       --query properties.latestRevisionName -o tsv)
   ```
4. Verify with `GET /health/ready` and by tailing logs for connection
   errors.

## Apply database migrations

Deployments run a dedicated migration job before workloads roll. Manually:

```bash
# Locally
make migrate

# In Azure: start the migration Container Apps Job
az containerapp job start -g $RG --name <migration-job-name>
```

## Roll back an image

Images are tagged with the git SHA that built them, so rollback is
redeploying an older SHA:

- Preferred: re-run the `deploy-dev` workflow from the older commit
  (Actions → deploy-dev → Run workflow on the desired ref). This keeps
  Terraform and images consistent.
- Fast path for one app:
  ```bash
  az containerapp update -g $RG --name <api-app-name> \
    --image <acr>.azurecr.io/oeop-api:<old-sha>
  ```
  Note: the next full deploy will supersede a manual image pin.

## Disable public submissions

Set the kill switch and restart the API:

```bash
az containerapp update -g $RG --name <api-app-name> \
  --set-env-vars OEOP_SUBMISSIONS_ENABLED=false
```

Submissions return a problem+json error while reads continue to work.
`DEMO_MODE` (predefined regions only, tighter limits) is controlled the same
way. See [security.md](security.md#api-hardening).

## Clean old artifacts

- **Automatic:** a blob lifecycle policy deletes artifacts after 30 days
  (retention is configurable).
- **Manual (one analysis):**
  ```bash
  az storage blob delete-batch --account-name <storage-account> \
    --auth-mode login -s <container> --pattern "analyses/<analysis_id>/*"
  ```
  Then delete or mark the corresponding `artifacts` rows so the API stops
  offering downloads.

## Destroy the dev environment safely

Use the `destroy-dev` workflow (Actions → destroy-dev), which requires a
typed confirmation of the environment name before running
`terraform destroy`. Do not destroy resources ad hoc with `az` — Terraform
state must remain the source of truth. Costs while idle are dominated by the
PostgreSQL Flexible Server; see
[cost-and-scaling.md](cost-and-scaling.md#shutting-down) for cheaper
alternatives to full destruction.

## Deleting an analysis

Removes the database records **and** the stored artifacts. Blobs are deleted
before the rows so an interruption leaves visible, recoverable state rather
than orphaned blobs nothing references.

```bash
# Always preview first — this is irreversible.
oeop-admin delete-analysis --analysis-id <uuid> --dry-run

# Delete specific analyses
oeop-admin delete-analysis --analysis-id <uuid> --analysis-id <uuid>

# Delete every analysis from a processing generation older than the canonical
# grid (major version < 2); those are not comparable across dates when the AOI
# crossed a Sentinel-2 tile boundary.
oeop-admin delete-analysis --legacy --dry-run
oeop-admin delete-analysis --legacy
```

Two guards refuse to run without `--force`:

- the analysis the public landing page currently links to (deleting it would
  leave a dead demo link — seed a replacement first), and
- anything still `queued` or `running` (that is work in flight, not a stale
  record, and deleting it would strand a queue message).

`--legacy` keys on `processing_version`, **not** on whether a grid is present:
a queued analysis has no grid yet either, so the naive filter would delete
work in flight.

In Azure the database is VNet-private, so run the command inside the deployed
API container:

```bash
az containerapp exec -g rg-oeop-dev -n ca-oeop-dev-api \
  --command "python -m oeop_api.cli delete-analysis --legacy --dry-run"
```

### Do not use `az containerapp job start --command` for this

It looks like a natural fit — the seed job already carries the API image and
the database credentials — but on older Azure CLI (confirmed on 2.49.0) it
fails dangerously:

- `--command "/bin/sh" "-c" "..."` is rejected outright, because the CLI's own
  argument parser consumes `-c`.
- Working around that by joining the parts into one comma-separated string is
  **accepted, and silently does nothing**. The override is not applied, the job
  runs its *configured* command, and the execution reports `Succeeded`.

For the seed job the configured command is `seed-regions && seed-demo`, so a
delete that appears to succeed has actually reseeded the database. Never treat
a `Succeeded` execution as proof a delete happened — confirm the analysis
returns 404 from the API.

If a job really is the only route, override through ARM, which does apply it.
Send the container's existing spec back with only `command` changed, or the
override drops its environment and the container cannot reach the database:

```bash
az containerapp job show -g $RG -n <job-name> \
  --query "properties.template.containers[0]" -o json > container.json
# edit container.json: set "command", remove "args"
python3 -c "import json;print(json.dumps({'containers':[json.load(open('container.json'))]}))" > body.json

az rest --method post \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.App/jobs/<job-name>/start?api-version=2023-05-01" \
  --body @body.json
```

