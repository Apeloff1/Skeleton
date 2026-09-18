#!/usr/bin/env python3
"""Fail closed when Track E root sprawl returns.

Exit 0 — root is clean of *_test.py / test_*.py / test_result.md / *.bak
Exit 2 — violations present
Exit 1 — usage / unexpected error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skeleton.artifact_plane.track_e import TrackEAuditor  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    auditor = TrackEAuditor(args.root)
    card = auditor.audit()
    if args.json:
        print(json.dumps(card, sort_keys=True))
    else:
        stray = card.get("stray_root_tests") or []
        bak = card.get("stray_bak") or []
        if card.get("hit") == 1:
            print("track-e: OK (no root test sprawl)")
        else:
            print("track-e: rejected root sprawl:", file=sys.stderr)
            for name in stray:
                print(f"  - root test: {name}", file=sys.stderr)
            for name in bak:
                print(f"  - root bak: {name}", file=sys.stderr)
            print("Move files to tests/legacy_root/ or scripts/archive_root_tests/. Do not delete.", file=sys.stderr)
            print("See docs/ARTIFACT_PLANE.md (GB-8).", file=sys.stderr)
    return auditor.fail_closed()


if __name__ == "__main__":
    raise SystemExit(main())
