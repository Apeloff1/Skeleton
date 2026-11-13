"""Brew 0026.
"""
from __future__ import annotations

BREW = "brew_0026"

def mix(reagents: list[str]) -> dict:
    if len(reagents) < 2:
        return {"ok": False, "reason": "need_two"}
    return {"ok": True, "brew": BREW, "potion": f"potion_{26}"}
