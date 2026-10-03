"""CLI: ``python -m skeleton.ops.cockpit <command> ...``

Commands:
  brand-check [--root DIR] [--canvas]      exit 1 on blocking brand warnings
  smoke-compare CURRENT.json BASELINE.json exit 3 if diverged, else exit_code_for(current)
  migrations-pending DIR [--applied a.sql,b.sql]
  guard-url URL                            exit 1 if not loopback (unless opted out)
  flight PROBE.json                        evaluate a qa-flight probe dump
  with-app-env [--root DIR] -- CMD ...     run CMD with .grok/app-env.json VITE_* merged
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import (
    app_env,
    brand_check,
    browser_guard,
    migration_plan,
    qa_flight,
    smoke_verdict,
)


def _p(obj) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["with-app-env"]:
        rest = argv[1:]
        root = "."
        if rest[:1] == ["--root"] and len(rest) >= 2:
            root, rest = rest[1], rest[2:]
        if rest[:1] == ["--"]:
            rest = rest[1:]
        if not rest:
            print(
                "usage: with-app-env [--root DIR] -- <command> [args...]",
                file=sys.stderr,
            )
            return 2
        return app_env.run_with_app_env(rest, root)

    ap = argparse.ArgumentParser(prog="skeleton.ops.cockpit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brand-check")
    b.add_argument("--root", default=".")
    b.add_argument("--canvas", action="store_true")
    s = sub.add_parser("smoke-compare")
    s.add_argument("current")
    s.add_argument("baseline")
    m = sub.add_parser("migrations-pending")
    m.add_argument("dir")
    m.add_argument("--applied", default="")
    g = sub.add_parser("guard-url")
    g.add_argument("url")
    f = sub.add_parser("flight")
    f.add_argument("probe")
    f.add_argument("--min-delta", type=float, default=qa_flight.DEFAULT_MIN_DELTA)
    a = ap.parse_args(argv)

    if a.cmd == "brand-check":
        findings = brand_check.compute_brand_warnings(
            has_canvas=a.canvas, workspace_root=a.root
        )
        _p([{"level": x.level, "code": x.code, "message": x.message} for x in findings])
        return 0 if brand_check.brand_ok(findings) else 1
    if a.cmd == "smoke-compare":
        cur = json.loads(Path(a.current).read_text("utf-8"))
        cmp = smoke_verdict.baseline_comparison(
            cur, Path(a.baseline).read_text("utf-8")
        )
        _p(cmp.to_dict())
        return (
            3
            if cmp.diverges_from_baseline
            else smoke_verdict.exit_code_for(cur.get("viewports"))
        )
    if a.cmd == "migrations-pending":
        applied = [x for x in a.applied.split(",") if x]
        pend = migration_plan.pending_migrations(
            migration_plan.scan_dir(a.dir), applied
        )
        _p([{"name": x.name, "path": x.path} for x in pend])
        return 0
    if a.cmd == "guard-url":
        try:
            browser_guard.checked_url(a.url)
        except browser_guard.GuardError as exc:
            _p({"ok": False, "error": str(exc)})
            return 1
        _p({"ok": True, "url": a.url})
        return 0
    if a.cmd == "flight":
        dump = json.loads(Path(a.probe).read_text("utf-8"))
        probe = qa_flight.FlightProbe.from_dict(dump.get("probe"))
        v = qa_flight.evaluate_flight(
            probe, dump.get("errors") or [], min_delta=a.min_delta
        )
        _p({"passed": v.passed, "dA": v.d_a, "dD": v.d_d, "failures": v.failures})
        return 0 if v.passed else 1
    return 2  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
