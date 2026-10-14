#!/usr/bin/env python3
"""Fail-closed verifier for hostile gap G013 control/data plane isolation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.security.control_data_isolation import (
    ControlDataIsolationError,
    validate_repository_control_data_isolation,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = validate_repository_control_data_isolation(ROOT)
    except ControlDataIsolationError as exc:
        print(f"control/data plane isolation: rejected: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.payload(), indent=2, sort_keys=True))
    elif report.valid:
        print(
            "control/data plane isolation: OK "
            f"({report.plane_count} planes; "
            f"{len(report.control_planes)} control / "
            f"{len(report.data_planes)} data)"
        )
    else:
        for error in report.errors:
            print(f"  - {error}", file=sys.stderr)
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
