"""``python -m skeleton.perf_profiler`` command line.

Subcommands (exit 0 = pass, 1 = gate failed / invalid evidence, 2 = usage error):

* ``frames``  read frame durations (JSON list of ms, file or ``-``), print stats
  (percentiles from main's observability profiler) and fail if the hitch ratio
  exceeds ``--max-hitch-ratio``. Empty input fails closed.
* ``alloc``   call ``module:function`` (no args) under the allocation tracker
  and fail if net ``alloc_bytes`` or ``peak_bytes`` exceed the given limits.
* ``verify``  check the sha256 seal of a load report written by ``LoadTimer``.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from typing import Any, Callable, List, Optional, Sequence

from .alloc import AllocationTracker
from .frames import FrameSampler
from .load_timers import verify_report


class UsageError(Exception):
    pass


def _read_json(path: str) -> Any:
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read JSON from {path}: {exc}") from exc


def _resolve(target: str) -> Callable[[], Any]:
    module_name, sep, attr = target.partition(":")
    if not sep or not module_name or not attr:
        raise UsageError("target must look like 'package.module:function'")
    try:
        fn = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise UsageError(f"cannot resolve {target}: {exc}") from exc
    if not callable(fn):
        raise UsageError(f"{target} is not callable")
    return fn


def _cmd_frames(args: argparse.Namespace) -> int:
    data = _read_json(args.input)
    if not isinstance(data, list):
        raise UsageError("frames input must be a JSON list of numbers")
    sampler = FrameSampler(budget_ms=args.budget_ms, capacity=max(1, len(data)), hitch_factor=args.hitch_factor)
    try:
        for value in data:
            sampler.record(value)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    stats = sampler.stats()
    passed = stats.within_budget(args.max_hitch_ratio)
    print(json.dumps({"pass": passed, **stats.to_dict()}, sort_keys=True))
    return 0 if passed else 1


def _cmd_alloc(args: argparse.Namespace) -> int:
    fn = _resolve(args.target)
    with AllocationTracker(top_n=args.top) as tracker:
        with tracker.scope(args.target) as result:
            fn()
    failures: List[str] = []
    if args.max_alloc_bytes is not None and result.alloc_bytes > args.max_alloc_bytes:
        failures.append("alloc_bytes")
    if args.max_peak_bytes is not None and result.peak_bytes > args.max_peak_bytes:
        failures.append("peak_bytes")
    print(json.dumps({"pass": not failures, "failures": failures, **result.to_dict()}, sort_keys=True))
    return 1 if failures else 0


def _cmd_verify(args: argparse.Namespace) -> int:
    ok = verify_report(_read_json(args.report))
    print(json.dumps({"pass": ok}))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m skeleton.perf_profiler")
    sub = parser.add_subparsers(dest="command", required=True)

    frames = sub.add_parser("frames", help="frame-time stats and hitch gate")
    frames.add_argument("input", help="JSON list of frame durations in ms, or '-'")
    frames.add_argument("--budget-ms", type=float, default=1000.0 / 60.0)
    frames.add_argument("--hitch-factor", type=float, default=1.0)
    frames.add_argument("--max-hitch-ratio", type=float, default=0.0)
    frames.set_defaults(func=_cmd_frames)

    alloc = sub.add_parser("alloc", help="allocation profile of module:function")
    alloc.add_argument("target")
    alloc.add_argument("--max-alloc-bytes", type=int)
    alloc.add_argument("--max-peak-bytes", type=int)
    alloc.add_argument("--top", type=int, default=0)
    alloc.set_defaults(func=_cmd_alloc)

    verify = sub.add_parser("verify", help="verify a sealed load report")
    verify.add_argument("report")
    verify.set_defaults(func=_cmd_verify)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        return int(args.func(args))
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
