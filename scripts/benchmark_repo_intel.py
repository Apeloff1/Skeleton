#!/usr/bin/env python3
"""Benchmark cold/warm canonical repository-intelligence refreshes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import statistics
import sys
import time

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_index  # noqa: E402

ROOT = repo_index.ROOT


def run_once(out: Path, base_ref: str) -> tuple[float, dict]:
    started = time.perf_counter()
    snapshot = repo_index.snapshot_command(out, base_ref)
    wall_ms = (time.perf_counter() - started) * 1000
    return wall_ms, snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--out", type=Path, default=ROOT / ".cache" / "repo-intel-benchmark")
    args = parser.parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True, exist_ok=True)

    cold_ms, cold_snapshot = run_once(args.out, args.base)
    warm: list[float] = []
    warm_snapshots: list[dict] = []
    for _ in range(args.runs):
        wall, snapshot = run_once(args.out, args.base)
        warm.append(wall)
        warm_snapshots.append(snapshot)

    cold_metrics = cold_snapshot["metrics"]
    warm_metrics = [snapshot["metrics"] for snapshot in warm_snapshots]
    budgets = repo_index.base.load_json("quality-budgets.json")["index_performance_targets"]
    report = {
        "schema": 2,
        "source_digest": cold_snapshot["source_digest"],
        "tracked_files": cold_snapshot["tracked_files"],
        "tracked_bytes": cold_snapshot["tracked_bytes"],
        "graph_nodes": cold_metrics["graph_nodes"],
        "graph_edges": cold_metrics["graph_edges"],
        "external_dependency_components": cold_metrics.get("external_dependency_components", 0),
        "cold_wall_ms": round(cold_ms, 3),
        "warm_runs_ms": [round(x, 3) for x in warm],
        "warm_median_ms": round(statistics.median(warm), 3),
        "warm_min_ms": round(min(warm), 3),
        "warm_max_ms": round(max(warm), 3),
        "warm_cache_hit_ratios": [m.get("semantic_cache_hit_ratio", 0.0) for m in warm_metrics],
        "cold_metrics": cold_metrics,
        "last_warm_metrics": warm_metrics[-1],
        "targets": budgets,
        "target_observations": {
            "warm_refresh_within_target": statistics.median(warm) <= float(budgets["warm_refresh_ms"]),
            "cache_hit_ratio_within_target": warm_metrics[-1].get("semantic_cache_hit_ratio", 0.0) >= float(budgets["cache_hit_ratio_target"]),
        },
        "note": "These measurements apply only to this repository tree, runner and toolchain. They are evidence, not universal performance claims."
    }
    target = args.out / "benchmark.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
