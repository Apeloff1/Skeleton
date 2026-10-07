#!/usr/bin/env python3
"""Fail closed when the GB-11 plane audit ledger is broken.

Exit 0 — ledger present, scores legal, no stored_prose
Exit 2 — violations
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skeleton.artifact_plane.plane_audit import PlaneAudit  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    card = PlaneAudit(args.root).audit()
    if args.json:
        print(json.dumps(card, sort_keys=True))
    elif card.get("hit") == 1:
        print("plane-audit: OK n=" + str(card.get("n")))
    else:
        print("plane-audit: rejected", file=sys.stderr)
        for key in ("bad_score", "missing_fields", "prose", "unscored_on_disk"):
            for item in card.get(key) or []:
                print(f"  - {key}: {item}", file=sys.stderr)
        if not card.get("ledger_present"):
            print("  - missing docs/lineage/plane_audit.jsonl", file=sys.stderr)
    return 0 if card.get("hit") == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
