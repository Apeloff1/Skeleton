#!/usr/bin/env python3
"""Fail-closed verifier for the topology-wide G012 disaster-recovery contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.reliability.disaster_recovery_contract import (
    DisasterRecoveryContractError,
    validate_repository_disaster_recovery,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = validate_repository_disaster_recovery(ROOT)
    except DisasterRecoveryContractError as exc:
        print(f"disaster recovery contract: rejected: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.payload(), indent=2, sort_keys=True))
    elif report.valid:
        print(
            "disaster recovery contract: OK "
            f"({len(report.source_of_truth_domains)} source-of-truth domains; "
            f"{len(report.required_backup_stores)} required backup stores)"
        )
    else:
        for error in report.errors:
            print(f"  - {error}", file=sys.stderr)
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
