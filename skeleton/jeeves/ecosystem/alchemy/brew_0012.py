"""Brew 0012.
"""
from __future__ import annotations

BREW = "brew_0012"

def mix(reagents: list[str]) -> dict:
    if len(reagents) < 2:
        return {"ok": False, "reason": "need_two"}
    return {"ok": True, "brew": BREW, "potion": f"potion_{12}"}
