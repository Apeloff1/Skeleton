"""Battle pass 0004.
"""
from __future__ import annotations

PASS = "pass_0004"

def reward(level: int) -> dict:
    if level < 1:
        return {"ok": False, "reason": "bad_level"}
    return {"ok": True, "pass": PASS, "level": level, "item": f"bp_item_{level}"}
