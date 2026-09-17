#!/usr/bin/env python3
"""Fail-closed emit-pack checker. No Godot binary. Exit 0 only on a complete tree."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED = (
    "project.godot",
    "world.json",
    "world.gd",
    "world.tscn",
    "player.gd",
    "jeeves",
    "heat",
    "forge",
    "extract",
    "reports/build_report.md",
    "data/spec.json",
)
FORBIDDEN = ("backend/godot", "godot.exe", "__pycache__", ".env")


def check_dir(root: Path) -> dict:
    missing = []
    for name in REQUIRED:
        path = root / name
        if name in {"jeeves", "heat", "forge", "extract"}:
            if not path.is_dir():
                missing.append(name + "/")
            continue
        if not path.is_file():
            missing.append(name)
    banned = []
    for rel in root.rglob("*"):
        text = str(rel.relative_to(root)).replace("\\", "/")
        lowered = text.lower()
        for token in FORBIDDEN:
            if token in lowered:
                banned.append(text)
    return {
        "kind": "gamefile-ops",
        "root": str(root),
        "missing": missing,
        "banned": banned,
        "valid": 0 if missing or banned else 1,
        "fixes": 0,
        "godot_binary": 0,
        "stored_prose": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--card":
        from skeleton.game.emit_tree import build, public_card

        print(json.dumps(public_card(build()), indent=2))
        return 0
    if not args:
        print(json.dumps({"ok": False, "error": "usage: check_emit_pack.py <dir>|--card"}, indent=2))
        return 2
    root = Path(args[0])
    if not root.is_dir():
        print(json.dumps({"ok": False, "error": "missing dir"}, indent=2))
        return 2
    payload = check_dir(root)
    print(json.dumps(payload, indent=2))
    return 0 if payload["valid"] == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
