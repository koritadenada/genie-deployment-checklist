"""Genie Agent benchmark gate.

Runs every benchmark question of a Genie Agent, waits for the evaluation, and passes only when
accuracy is above --min-accuracy. On failure it prints each failing question with the reason
Genie's evaluator gave, then raises, so the job run fails and Databricks sends the failure email.

Runs as a Databricks job task (see resources/benchmark_gate.job.yml) or locally:
    python src/benchmark_gate.py --space-id <id> --min-accuracy 80
Uses the Genie benchmark evaluation API (Beta).
"""
import argparse
import json
import time

from databricks.sdk import WorkspaceClient

FINAL = {"DONE", "EVALUATION_FAILED", "EVALUATION_CANCELLED", "EVALUATION_TIMEOUT"}

REASONS = {
    "EMPTY_RESULT": "the query returned no rows",
    "EMPTY_GOOD_SQL": "the expected SQL returned no rows",
    "RESULT_MISSING_ROWS": "rows are missing compared with the expected result",
    "RESULT_EXTRA_ROWS": "there are extra rows compared with the expected result",
    "RESULT_MISSING_COLUMNS": "columns are missing compared with the expected result",
    "RESULT_EXTRA_COLUMNS": "there are extra columns compared with the expected result",
    "SINGLE_CELL_DIFFERENCE": "a value differs from the expected result",
    "COLUMN_TYPE_DIFFERENCE": "a column has a different type than expected",
    "LLM_JUDGE_MISSING_OR_INCORRECT_FILTER": "a filter is missing or wrong",
    "LLM_JUDGE_WRONG_FILTER": "a filter is wrong",
    "LLM_JUDGE_MISSING_OR_INCORRECT_AGGREGATION": "an aggregation is missing or wrong",
    "LLM_JUDGE_WRONG_AGGREGATION": "an aggregation is wrong",
    "LLM_JUDGE_MISSING_OR_INCORRECT_JOIN": "a join is missing or wrong",
    "LLM_JUDGE_MISSING_JOIN": "a join is missing",
    "LLM_JUDGE_INCORRECT_TABLE_OR_FIELD_USAGE": "the wrong table or column was used",
    "LLM_JUDGE_WRONG_COLUMNS": "the wrong columns were returned",
    "LLM_JUDGE_INCORRECT_METRIC_CALCULATION": "a metric is calculated incorrectly",
    "LLM_JUDGE_INCORRECT_FUNCTION_USAGE": "a function is used incorrectly",
    "LLM_JUDGE_INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC": "business logic or an instruction was not followed",
    "LLM_JUDGE_MISINTERPRETATION_OF_USER_REQUEST": "the question was misinterpreted",
    "LLM_JUDGE_INCOMPLETE_OR_PARTIAL_OUTPUT": "the answer is incomplete",
    "LLM_JUDGE_FORMATTING_ERROR": "the output is formatted incorrectly",
    "LLM_JUDGE_SEMANTIC_ERROR": "the SQL has a semantic error",
    "LLM_JUDGE_SYNTAX_ERROR": "the SQL has a syntax error",
    "LLM_JUDGE_OTHER": "the evaluator flagged another problem",
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--space-id", required=True)
    p.add_argument("--min-accuracy", type=float, default=80.0, help="accuracy must be above this percentage")
    p.add_argument("--target", default="")
    p.add_argument("--timeout-minutes", type=int, default=45)
    return p.parse_args()


def response_text(responses):
    for r in responses or []:
        if r.get("response"):
            return " ".join(str(r["response"]).split())
    return ""


def main():
    a = parse_args()
    w = WorkspaceClient()
    api = w.api_client
    base = f"/api/2.0/genie/spaces/{a.space_id}/eval-runs"
    space = api.do("GET", f"/api/2.0/genie/spaces/{a.space_id}")
    name = space.get("title", a.space_id)

    run = api.do("POST", base, body={})
    run_id = run["eval_run_id"]
    print(f"Benchmark run {run_id} started for '{name}' ({a.target or 'no target'})", flush=True)

    deadline = time.time() + a.timeout_minutes * 60
    delay = 5
    while True:
        run = api.do("GET", f"{base}/{run_id}")
        status = run.get("eval_run_status", "NOT_STARTED")
        print(f"  {status}: {run.get('num_done', 0)}/{run.get('num_questions', '?')} questions evaluated", flush=True)
        if status in FINAL:
            break
        if time.time() > deadline:
            raise RuntimeError(f"Benchmark run {run_id} did not finish within {a.timeout_minutes} minutes")
        time.sleep(delay)
        delay = min(delay * 2, 60)

    results, token = [], None
    while True:
        page = api.do("GET", f"{base}/{run_id}/results", query={"page_size": 100, **({"page_token": token} if token else {})})
        results += page.get("eval_results", [])
        token = page.get("next_page_token")
        if not token:
            break

    total = run.get("num_questions") or len(results)
    correct = run.get("num_correct") or 0
    accuracy = 100.0 * correct / total if total else 0.0

    failures = []
    for r in results:
        d = api.do("GET", f"{base}/{run_id}/results/{r['result_id']}")
        assessment = d.get("assessment", "NEEDS_REVIEW")
        if assessment == "GOOD":
            continue
        reasons = [REASONS.get(x, x) for x in d.get("assessment_reasons", [])] or (
            ["needs manual review"] if assessment == "NEEDS_REVIEW" else ["no reason given"])
        failures.append({
            "question": r.get("question", ""),
            "assessment": assessment,
            "reasons": reasons,
            "genie_sql": response_text(d.get("actual_response"))[:400],
        })

    passed = status == "DONE" and accuracy > a.min_accuracy
    print("")
    print("=" * 72)
    print(f"GENIE BENCHMARK GATE  {'PASSED' if passed else 'FAILED'}")
    print(f"Agent: {name}   Target: {a.target}   Run: {run_id}")
    print(f"Accuracy: {accuracy:.1f}% ({correct}/{total} correct)   Required: above {a.min_accuracy:g}%")
    print("=" * 72)
    for i, f in enumerate(failures, 1):
        print(f"{i:>2}. [{f['assessment']}] {f['question']}")
        print(f"    Reason: {'; '.join(f['reasons'])}")
        if f["genie_sql"]:
            print(f"    Genie answered: {f['genie_sql']}")
    summary = {"passed": passed, "accuracy": round(accuracy, 1), "correct": correct, "total": total,
               "min_accuracy": a.min_accuracy, "status": status, "eval_run_id": run_id, "space_id": a.space_id,
               "target": a.target, "failures": failures}
    print("GATE_RESULT_JSON " + json.dumps(summary), flush=True)

    if not passed:
        why = (f"benchmark run ended with status {status}" if status != "DONE"
               else f"accuracy {accuracy:.1f}% ({correct}/{total}) is not above {a.min_accuracy:g}%")
        top = "; ".join(f"'{f['question']}': {', '.join(f['reasons'])}" for f in failures[:10])
        raise RuntimeError(f"Genie benchmark gate failed for '{name}' in {a.target}: {why}. Failing questions: {top}")


if __name__ == "__main__":
    main()
