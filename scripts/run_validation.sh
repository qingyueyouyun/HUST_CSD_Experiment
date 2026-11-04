#!/usr/bin/env bash
# Baseline vs hybrid validation on the course 1M YFCC index.
# Each case is repeated 3 times; logs are written to $OUT.
set -euo pipefail

REPO=${REPO:-/home/xwc/gateann-hybrid-dev}
ROOT=${ROOT:-/home/xwc/fvs-course-lab}
IDX=${IDX:-$ROOT/course_runs/indices/gateann/formal_1000000/yfcc}
DS=${DS:-$ROOT/datasets/yfcc_course_v1/formal_1000000}
OUT=${OUT:-/home/xwc/hybrid-results}
BIN=$REPO/build/tests/search_disk_index_yfcc

mkdir -p "$OUT"

run_case() {
  local label=$1 bucket=$2; shift 2
  local workload=$DS/workloads/$bucket
  echo ">>> $label"
  "$BIN" uint8 "$IDX" 1 8 "$workload/query.u8bin" \
    "$DS/base.metadata.spmat" "$workload/query.metadata.spmat" \
    "$workload/ground_truth.ids.ibin" 10 l2 pq 8 0 0 32 "$@" \
    > "$OUT/$label.log" 2>&1
}

for r in 1 2 3; do
  run_case "baseline-low-r$r" low 320 640 1280 2560
  run_case "baseline-medium-r$r" medium 320
  run_case "baseline-high-r$r" high 320

  run_case "hybrid-low-h3b128-r$r" low 320 --hybrid=1 --relay-hops=3 --relay-budget=128 --relay-total-budget=2048
  run_case "hybrid-low-h3b256-r$r" low 320 --hybrid=1 --relay-hops=3 --relay-budget=256 --relay-total-budget=4096
  run_case "hybrid-low-h2b128-r$r" low 320 --hybrid=1 --relay-hops=2 --relay-budget=128 --relay-total-budget=2048
  run_case "hybrid-medium-r$r" medium 320 --hybrid=1 --relay-hops=3 --relay-budget=128 --relay-total-budget=2048
  run_case "hybrid-high-r$r" high 320 --hybrid=1 --relay-hops=3 --relay-budget=128 --relay-total-budget=2048
done

echo "done: $OUT"
