#!/usr/bin/env bash
# One-command batch runbook: raw transcripts -> scored corpus -> dashboard.
#
#   ./scripts/run_pipeline.sh                       # full run, 8 workers
#   WORKERS=4 ./scripts/run_pipeline.sh             # fewer parallel claude calls
#   ./scripts/run_pipeline.sh --baseline old/results  # extra args go to build_report
#
# For a NEW BATCH of calls, DON'T use this script — use the batch utility,
# which stages into batches/<name>/, gates the judge, and auto-links deltas:
#     python3 scripts/new_batch.py /path/to/new_txt_folder [--deploy]
# This script re-runs the pipeline in place on the ORIGINAL corpus only.
# Every stage is checkpointed, so re-running resumes where it stopped.
#
# The judge gate: compare.py prints agreement vs the 18 golden labels. If it
# drops below ~99%, STOP — the judge moved; do not trust the batch scores.
set -euo pipefail
cd "$(dirname "$0")/.."
W="${WORKERS:-8}"

echo "== 1/6 parse raw transcripts -> data/calls.jsonl"
python3 scripts/parse.py

echo "== 2/6 two-pass judge (extract + rubric), ${W} workers"
python3 scripts/run_eval.py --workers "$W"

echo "== 3/6 judge-vs-golden gate (must stay >= 99%)"
python3 scripts/compare.py

echo "== 4/6 corpus aggregation -> results/summary.json"
python3 scripts/analyze.py

echo "== 5/6 transfer-containment pass, ${W} workers"
python3 scripts/containment.py --workers "$W"

echo "== 6/6 dashboard -> report/final_report.html"
python3 scripts/build_report.py "$@"

echo "Done. Open report/final_report.html"
