#!/usr/bin/env python3
"""Compatibility entry point for the P2-T1 tranche state.

T1 is now activated.  The historical prepared-plan checker name remains in
older authority documents, so this module deliberately delegates to the
activated-state validator instead of retaining stale 42/272 assertions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from scripts.check_p2_tranche1_activated import (
    P2T1ActivationError as P2Tranche1Error,
    validate as _validate_activated,
)


ROOT = Path(__file__).resolve().parents[1]


def validate(root: Path = ROOT) -> dict[str, object]:
    result = dict(_validate_activated(root))
    result["tranche_state"] = "activated"
    result["selected_volume_count"] = 15
    result["workstream_count"] = 5
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(ROOT)
    except P2Tranche1Error as exc:
        print(f"P2 tranche 1 state: rejected: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("P2 tranche 1 state: ACTIVATED (57 scheduled / 257 queued)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
