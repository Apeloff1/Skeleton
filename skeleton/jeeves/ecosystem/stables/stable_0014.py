"""Stable 0014.
"""
from __future__ import annotations

STABLE = "stable_0014"

def board(mount: str) -> dict:
    if not mount:
        return {"ok": False, "reason": "no_mount"}
    return {"ok": True, "stable": STABLE, "mount": mount}
