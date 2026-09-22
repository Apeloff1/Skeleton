"""Diff last two scoreboards."""
from __future__ import annotations

import json
from typing import Any, Dict

from skeleton.kernel.persist import board_path, prev_board_path


def card(*, root=None) -> Dict[str, Any]:
    def _read(p):
        if not p.is_file():
            return set()
        try:
            return set(json.loads(p.read_text(encoding="utf-8")).get("names") or [])
        except Exception:
            return set()

    now = _read(board_path(root))
    was = _read(prev_board_path(root))
    return {
        "kind": "kernel-diff",
        "added": sorted(now - was),
        "removed": sorted(was - now),
        "now_n": len(now),
        "was_n": len(was),
        "stored_prose": 0,
    }
