#!/usr/bin/env python3
"""Historical P2-T1 activation compiler compatibility fence.

The activation has already been applied to canonical P2 state.  Re-running the
old proposal compiler would create duplicate ownership, so this entry point now
fails closed and directs callers to the activated-state validator.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


class P2Tranche1ActivationError(RuntimeError):
    pass


def build_activation_proposal(root: Path = ROOT):
    raise P2Tranche1ActivationError(
        "P2-T1 is already activated; use scripts/check_p2_tranche1_activated.py"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.parse_args()
    print(
        "P2 tranche 1 activation proposal: BLOCKED: P2-T1 is already activated",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
