"""``python -m skeleton.perfgate`` - soak + budget + baseline gate.

Exit codes: 0 pass, 1 gate failed, 2 usage/config error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .baseline import Baseline, compare, load_baseline, save_baseline
from .budget import load_budgets
from .soak import SoakConfig, run_soak
from .workloads import resolve


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skeleton.perfgate")
    p.add_argument("--workload", action="append", required=True,
                   help="workload spec, e.g. forge_walk:soulslike (repeatable)")
    p.add_argument("--iterations", type=int, default=20)
    p.add_argument("--duration-s", type=float, default=None)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--budgets", type=Path, help="budget JSON")
    p.add_argument("--baseline", type=Path, help="baseline JSON to compare against")
    p.add_argument("--tolerance", type=float, default=0.20)
    p.add_argument("--write-baseline", type=Path, help="write a new baseline here")
    p.add_argument("--json", action="store_true", help="emit one JSON summary line")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        cfg = SoakConfig(args.iterations, args.duration_s, args.warmup)
        workloads = {spec: resolve(spec) for spec in args.workload}
        budgets = load_budgets(args.budgets) if args.budgets else None
        baseline = load_baseline(args.baseline) if args.baseline else None
    except (ValueError, KeyError, OSError) as exc:
        print(f"perfgate: config error: {exc}", file=sys.stderr)
        return 2

    results = {name: run_soak(name, fn, cfg) for name, fn in workloads.items()}
    summaries = {n: r.summary for n, r in results.items()}
    failures: List[str] = []
    for n, r in results.items():
        if r.aborted:
            failures.append(f"{n}: aborted after consecutive errors: {r.errors[-1]}")
        if not r.samples_ms:
            failures.append(f"{n}: no successful measured sample")
        if r.errors or r.warmup_errors:
            failures.append(f"{n}: workload errors, warmup={r.warmup_errors}, measured={len(r.errors)}")
    if budgets:
        failures += [str(v) for v in budgets.check(summaries)]
    report = compare(baseline, summaries, args.tolerance) if baseline else None
    if report:
        failures += [l for l in report.lines() if l.startswith(("REGRESSION", "missing workload"))]
    if args.write_baseline:
        if failures:
            failures.append("baseline publication held after failed qualification")
        else:
            try:
                save_baseline(Baseline.from_summaries(summaries), args.write_baseline)
            except (ValueError, OSError) as exc:
                failures.append("baseline publication held: " + type(exc).__name__)

    for n, s in summaries.items():
        print(f"{n}: n={s.count} err={s.errors} p50={s.p50_ms:.1f}ms "
              f"p95={s.p95_ms:.1f}ms max={s.max_ms:.1f}ms drift=x{s.drift_ratio:.2f}")
    if report:
        for line in report.lines():
            print(line)
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    if args.json:
        print(json.dumps({"ok": not failures, "failures": failures,
                          "summaries": {n: s.as_dict() for n, s in summaries.items()},
                          "device_qualified": False, "release_certified": False},
                         sort_keys=True, allow_nan=False))
    return 1 if failures else 0
