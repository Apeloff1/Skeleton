"""Executable game product acceptance with truthful exit status."""
from __future__ import annotations
import argparse
import json

from .io import write_new
from .qualification import run_matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-qualification")
    parser.add_argument("--fail-fast", action="store_true", help="stop after first failing contract")
    parser.add_argument("--output", help="create-only report path")
    args = parser.parse_args(argv)
    report = run_matrix(fail_fast=args.fail_fast)
    if args.output:
        try:
            write_new(args.output, report, 256_000)
        except (ValueError, OSError) as exc:
            parser.exit(2, f"ridge-qualification: {exc}\n")
    else:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
