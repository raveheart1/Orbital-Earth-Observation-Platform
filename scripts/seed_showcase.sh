#!/usr/bin/env bash
# Submit one showcase analysis per predefined region and wait for them all.
#
# Gives a fresh environment a browsable result for every region instead of only
# the demonstration region. Each analysis is a real run against live Sentinel-2
# imagery — nothing here is precomputed or synthetic.
#
#   API_URL=http://localhost:8000 ./scripts/seed_showcase.sh
#   API_URL=https://<deployed>    ./scripts/seed_showcase.sh
#
# Safe to re-run: regions that already have a succeeded analysis are skipped.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-2400}"
# Growing-season window in the northern hemisphere; southern-hemisphere regions
# still resolve because selection only needs scenes inside the range.
START="${START:-2024-01-01}"
END="${END:-2024-12-31}"
CLOUD="${CLOUD:-20}"
SCENES="${SCENES:-6}"

python_bin=$(command -v python3)

regions_json=$(curl -fsS "$API_URL/api/v1/regions")
existing=$(curl -fsS "$API_URL/api/v1/analyses?limit=100")

submitted=()
while IFS=$'\t' read -r slug region_id; do
  [ -z "$slug" ] && continue
  already=$(printf '%s' "$existing" | "$python_bin" -c "
import json,sys
d=json.load(sys.stdin)
print(any(
    (a.get('region') or {}).get('slug') == '$slug' and a['status'] in ('succeeded','queued','running')
    for a in d['items']
))")
  if [ "$already" = "True" ]; then
    echo "  skip   $slug (already has an analysis)"
    continue
  fi
  aid=$(curl -fsS -X POST "$API_URL/api/v1/analyses" \
    -H 'Content-Type: application/json' \
    -d "{\"region_id\":\"$region_id\",\"start_date\":\"$START\",\"end_date\":\"$END\",\"max_cloud_cover_pct\":$CLOUD,\"scene_limit\":$SCENES}" \
    | "$python_bin" -c 'import json,sys; print(json.load(sys.stdin)["id"])')
  echo "  submit $slug -> $aid"
  submitted+=("$aid")
done < <(printf '%s' "$regions_json" | "$python_bin" -c "
import json,sys
for r in json.load(sys.stdin):
    print(r['slug'] + '\t' + r['id'])
")

if [ ${#submitted[@]} -eq 0 ]; then
  echo "Nothing to submit."
  exit 0
fi

echo "Waiting for ${#submitted[@]} analyses..."
elapsed=0
while (( elapsed < TIMEOUT_SECONDS )); do
  pending=0
  for aid in "${submitted[@]}"; do
    status=$(curl -fsS "$API_URL/api/v1/analyses/$aid" | "$python_bin" -c 'import json,sys; print(json.load(sys.stdin)["status"])')
    case "$status" in queued|running) pending=$((pending + 1));; esac
  done
  [ "$pending" -eq 0 ] && break
  echo "  [$elapsed s] $pending still processing"
  sleep 20
  elapsed=$((elapsed + 20))
done

echo
printf '%-34s %-10s %s\n' region status summary
for aid in "${submitted[@]}"; do
  curl -fsS "$API_URL/api/v1/analyses/$aid" | "$python_bin" -c '
import json, sys
a = json.load(sys.stdin)
slug = (a.get("region") or {}).get("slug", "custom")
s = a.get("summary") or {}
detail = ""
if a["status"] == "succeeded" and s.get("ndvi_mean_first") is not None:
    detail = "%d scenes, NDVI %.3f -> %.3f" % (
        s["usable_scene_count"], s["ndvi_mean_first"], s["ndvi_mean_last"])
elif a.get("failure"):
    detail = a["failure"].get("detail", "")[:60]
print("%-34s %-10s %s" % (slug, a["status"], detail))
'
done
