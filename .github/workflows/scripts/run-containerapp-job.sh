#!/usr/bin/env bash
# Helper sourced by deploy-dev.yml: start a Container Apps job and poll its
# execution until it succeeds, failing honestly on error or timeout.
#
# usage: run_containerapp_job <resource-group> <job-name> <timeout-seconds>

run_containerapp_job() {
  local rg="$1" job="$2" timeout="${3:-600}"
  echo "Starting Container Apps job '$job' in '$rg'"

  local exec_name
  exec_name=$(az containerapp job start \
    --resource-group "$rg" \
    --name "$job" \
    --query name -o tsv)
  echo "Execution: $exec_name (timeout: ${timeout}s)"

  local deadline=$((SECONDS + timeout)) status
  while [ "$SECONDS" -lt "$deadline" ]; do
    status=$(az containerapp job execution list \
      --resource-group "$rg" \
      --name "$job" \
      --query "[?name=='$exec_name'].properties.status | [0]" -o tsv 2>/dev/null || true)
    case "$status" in
      Succeeded)
        echo "Job '$job' succeeded."
        return 0
        ;;
      Failed | Stopped | Degraded)
        echo "::error::Job '$job' execution '$exec_name' finished with status '$status'. Check logs: az containerapp job logs show -g $rg -n $job"
        return 1
        ;;
      *)
        echo "  status=${status:-Pending} ..."
        sleep 10
        ;;
    esac
  done

  echo "::error::Job '$job' execution '$exec_name' did not finish within ${timeout}s."
  return 1
}
