#!/usr/bin/env bash
# Submit the demonstration analysis through the running local stack and wait
# for the worker to complete it. Requires: make dev && make migrate && make seed.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-1200}"

echo "Submitting demonstration analysis (Southeast Michigan, real Sentinel-2 data)..."
ANALYSIS_ID=$(uv run oeop-admin seed-demo | tail -1)
if [[ -z "$ANALYSIS_ID" ]]; then
  echo "Failed to submit demo analysis" >&2
  exit 1
fi
echo "Analysis: $ANALYSIS_ID"
echo "Status:   $API_URL/api/v1/analyses/$ANALYSIS_ID"
echo "Web:      http://localhost:3000/analyses/$ANALYSIS_ID"

elapsed=0
while (( elapsed < TIMEOUT_SECONDS )); do
  status=$(curl -fsS "$API_URL/api/v1/analyses/$ANALYSIS_ID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  echo "  [$elapsed s] status=$status"
  case "$status" in
    succeeded)
      echo "Demo analysis completed successfully."
      curl -fsS "$API_URL/api/v1/analyses/$ANALYSIS_ID" \
        | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["summary"], indent=2))'
      exit 0
      ;;
    failed|cancelled)
      echo "Demo analysis ended in status=$status" >&2
      curl -fsS "$API_URL/api/v1/analyses/$ANALYSIS_ID" \
        | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["failure"], indent=2))' >&2
      exit 1
      ;;
  esac
  sleep 10
  elapsed=$((elapsed + 10))
done

echo "Timed out after ${TIMEOUT_SECONDS}s waiting for the demo analysis" >&2
exit 1
