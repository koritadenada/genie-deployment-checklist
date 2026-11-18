#!/usr/bin/env bash
# Run the benchmark gate job for one target, print its report, and exit non-zero when it fails.
#   scripts/run_gate.sh <dev|staging|prod> [extra bundle options, for example --var warehouse_id=<id>]
# The job itself emails var.alert_email on failure; this script makes the reasons visible in CI
# (log and, on GitHub Actions, the job summary).
set -uo pipefail
TARGET="${1:?usage: run_gate.sh <target> [bundle options]}"
shift
cd "$(dirname "$0")/.."

JOB_ID=$(databricks bundle summary -t "$TARGET" "$@" -o json | jq -r '.resources.jobs.benchmark_gate.id')
[ -n "$JOB_ID" ] && [ "$JOB_ID" != "null" ] || { echo "benchmark_gate job not deployed for $TARGET"; exit 1; }

echo "Running the benchmark gate (job $JOB_ID) on $TARGET ..."
# Keep the run output out of the log here: the report is printed once, below, from the task output.
RUN_LOG=$(mktemp)
databricks bundle run benchmark_gate -t "$TARGET" "$@" > "$RUN_LOG" 2>&1
RC=$?
grep -E '^(Run URL|[0-9]{4}-[0-9]{2}-[0-9]{2} )' "$RUN_LOG"

# Print the task output (report, failing questions and reasons) whether the run passed or failed.
RUN_ID=$(databricks jobs list-runs --job-id "$JOB_ID" --limit 1 -o json | jq -r 'if type=="array" then .[0].run_id else .runs[0].run_id end')
TASK_RUN_ID=$(databricks jobs get-run "$RUN_ID" -o json | jq -r '.tasks[0].run_id')
OUT=$(databricks jobs get-run-output "$TASK_RUN_ID" -o json)
LOGS=$(echo "$OUT" | jq -r '.logs // ""')
echo "$LOGS" | grep -v '^GATE_RESULT_JSON '
echo "$OUT" | jq -r '.error // empty'

RESULT=$(echo "$LOGS" | sed -n 's/^GATE_RESULT_JSON //p' | tail -1)
if [ -n "${GITHUB_STEP_SUMMARY:-}" ] && [ -n "$RESULT" ]; then
  {
    echo "### Genie benchmark gate: $TARGET"
    echo "$RESULT" | jq -r '"**\(if .passed then "Passed" else "Failed" end)**: accuracy \(.accuracy)% (\(.correct)/\(.total)), required above \(.min_accuracy)%"'
    echo
    echo "$RESULT" | jq -r 'if (.failures|length) > 0 then "| Question | Assessment | Reason |\n|---|---|---|" else "All benchmark questions passed." end'
    echo "$RESULT" | jq -r '.failures[] | "| \(.question) | \(.assessment) | \(.reasons|join("; ")) |"'
  } >> "$GITHUB_STEP_SUMMARY"
fi

if [ "$RC" -ne 0 ]; then
  echo "Benchmark gate failed on $TARGET: the team was emailed and the pipeline stops here."
fi
exit "$RC"
