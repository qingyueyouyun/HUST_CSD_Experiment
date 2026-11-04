#!/usr/bin/env python3
"""Summarize baseline/hybrid GateANN validation logs into a CSV.

Log naming convention: <case>-r<N>.log, where <case> is e.g.
baseline-low, hybrid-low-h3b128, hybrid-medium. Each log may contain several
L rows (baseline-low runs L=320/640/1280/2560 in one process).
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROW = re.compile(r"^\s*(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*$")
HYBRID = re.compile(r"^\[hybrid\]\s+L=(\d+)\s+sel=([0-9.]+)\s+expansions=([0-9.]+)\s+relay_nodes=([0-9.]+)\s+relay_valid=([0-9.]+)")


def parse_log(path: Path) -> tuple[list[dict], dict[int, dict]]:
    rows: list[dict] = []
    hybrid: dict[int, dict] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = ROW.match(line)
        if match:
            values = [float(x) for x in match.groups()]
            rows.append({
                "L": int(values[0]),
                "qps": values[1],
                "recall": values[2] * 100.0,
                "mean_ios": values[3],
                "filter_skips": values[4],
                "io_us": values[5],
                "tunnel_us": values[6],
                "process_us": values[7],
            })
            continue
        match = HYBRID.match(line)
        if match:
            L = int(match.group(1))
            hybrid[L] = {
                "sel_est": float(match.group(2)),
                "relay_expansions": float(match.group(3)),
                "relay_nodes": float(match.group(4)),
                "relay_valid": float(match.group(5)),
            }
    return rows, hybrid


def median_range(values: list[float]) -> tuple[float, float, float]:
    return statistics.median(values), min(values), max(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logdir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    hybrid_meta: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for path in sorted(args.logdir.glob("*.log")):
        stem = path.stem
        if "-r" not in stem:
            continue
        case = stem.rsplit("-r", 1)[0]
        rows, hybrid = parse_log(path)
        for row in rows:
            groups[(case, row["L"])].append(row)
        for L, meta in hybrid.items():
            hybrid_meta[(case, L)].append(meta)

    fieldnames = [
        "case", "L", "repeats",
        "recall_median", "recall_min", "recall_max",
        "latency_us_median", "latency_us_min", "latency_us_max",
        "qps_median", "mean_ios_median", "filter_skips_median",
        "tunnel_us_median", "sel_est", "relay_expansions", "relay_nodes", "relay_valid",
    ]
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for (case, L), rows in sorted(groups.items()):
            latency = [1_000_000.0 / row["qps"] for row in rows]
            recall = [row["recall"] for row in rows]
            qps = [row["qps"] for row in rows]
            ios = [row["mean_ios"] for row in rows]
            skips = [row["filter_skips"] for row in rows]
            tunnel = [row["tunnel_us"] for row in rows]
            rec = median_range(recall)
            lat = median_range(latency)
            meta = hybrid_meta.get((case, L), [{}])
            writer.writerow({
                "case": case,
                "L": L,
                "repeats": len(rows),
                "recall_median": round(rec[0], 3),
                "recall_min": round(rec[1], 3),
                "recall_max": round(rec[2], 3),
                "latency_us_median": round(lat[0], 1),
                "latency_us_min": round(lat[1], 1),
                "latency_us_max": round(lat[2], 1),
                "qps_median": round(statistics.median(qps), 1),
                "mean_ios_median": round(statistics.median(ios), 2),
                "filter_skips_median": round(statistics.median(skips), 2),
                "tunnel_us_median": round(statistics.median(tunnel), 1),
                "sel_est": round(statistics.median([m["sel_est"] for m in meta if "sel_est" in m]), 4) if any("sel_est" in m for m in meta) else "",
                "relay_expansions": round(statistics.median([m["relay_expansions"] for m in meta if "relay_expansions" in m]), 1) if any("relay_expansions" in m for m in meta) else "",
                "relay_nodes": round(statistics.median([m["relay_nodes"] for m in meta if "relay_nodes" in m]), 0) if any("relay_nodes" in m for m in meta) else "",
                "relay_valid": round(statistics.median([m["relay_valid"] for m in meta if "relay_valid" in m]), 0) if any("relay_valid" in m for m in meta) else "",
            })
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
