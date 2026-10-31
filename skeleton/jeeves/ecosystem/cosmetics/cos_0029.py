"""Cosmetic 0029.
"""
from __future__ import annotations

COS = "cos_0029"

def equip(slot: str) -> dict:
    if slot not in ("head", "body", "weapon", "back"):
        return {"ok": False, "reason": "bad_slot"}
    return {"ok": True, "cos": COS, "slot": slot}
