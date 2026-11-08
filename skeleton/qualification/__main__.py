"""CLI: python -m skeleton.qualification --head <sha> [--cases DIR] [--evidence DIR] [--out FILE]

Exit codes: 0 all pass, 1 any fail, 2 any blocked (no fail), 3 schema error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import SchemaError
from .evidence import load_evidence
from .report import to_json, to_markdown
from .runner import run_cases
from .schema import load_cases
from .verdict import Verdict, aggregate

DEFAULT_CASES = Path(__file__).parent / "cases"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skeleton.qualification")
    ap.add_argument("--head", required=True)
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--evidence", default="artifacts/qualification/evidence")
    ap.add_argument("--out")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    args = ap.parse_args(argv)
    try:
        cases = load_cases(args.cases)
        evidence = load_evidence(args.evidence)
    except SchemaError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return 3
    results = run_cases(cases, evidence, args.head)
    text = (json.dumps(to_json(results, args.head), indent=2) + "\n"
            if args.format == "json" else to_markdown(results, args.head))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    overall = aggregate(results)
    return {Verdict.PASS: 0, Verdict.FAIL: 1, Verdict.BLOCKED: 2}[overall]


if __name__ == "__main__":
    raise SystemExit(main())
