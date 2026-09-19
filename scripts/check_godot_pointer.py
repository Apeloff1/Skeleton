#!/usr/bin/env python3
"""Fail closed when the Godot pointer is missing.

Exit 0 — pointer files present, blob not required
Exit 2 — missing pointer
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skeleton.artifact_plane.godot_locate import GodotLocator  # noqa: E402

POINTERS = (
    Path("godot.pointer"),
    Path("backend") / "godot.artifact.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    missing = [str(p) for p in POINTERS if not (root / p).is_file()]
    card = GodotLocator(root).locate()
    payload = {
        "kind": "godot-pointer-gate",
        "hit": 0 if missing else 1,
        "law": "GB-9",
        "missing": missing,
        "locate": card,
        "stored_prose": 0,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif missing:
        print("godot-pointer: missing", ", ".join(missing), file=sys.stderr)
        return 2
    else:
        print("godot-pointer: OK found=" + str(card.get("found")))
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
