"""Battle pass 0010.
"""
from __future__ import annotations

PASS = "pass_0010"

def reward(level: int) -> dict:
    if level < 1:
        return {"ok": False, "reason": "bad_level"}
    return {"ok": True, "pass": PASS, "level": level, "item": f"bp_item_{level}"}
