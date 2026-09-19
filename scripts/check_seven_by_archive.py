#!/usr/bin/env python3
"""Fail closed when SEVEN_BY_*.md returns to repository root.

Exit 0 — lane present, index present, no root volumes
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

from skeleton.artifact_plane.seven_by import SevenByAuditor  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    auditor = SevenByAuditor(args.root)
    card = auditor.audit()
    if args.json:
        print(json.dumps(card, sort_keys=True))
    elif card.get("hit") == 1:
        print("seven-by: OK (archive lane clean)")
    else:
        print("seven-by: rejected root volumes or missing lane:", file=sys.stderr)
        for name in card.get("stray_root") or []:
            print(f"  - root volume: {name}", file=sys.stderr)
        if not card.get("lane_present"):
            print("  - missing docs/archive/seven_by/", file=sys.stderr)
        if not card.get("index_present"):
            print("  - missing SEVEN_BY_INDEX.md in lane", file=sys.stderr)
        print("Move files to docs/archive/seven_by/. Do not rewrite volume bodies.", file=sys.stderr)
    return auditor.fail_closed()


if __name__ == "__main__":
    raise SystemExit(main())
