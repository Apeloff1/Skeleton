"""Parry 0012.
"""
from __future__ import annotations

PARRY = "parry_0012"

def window(timing: float) -> dict:
    perfect = abs(timing - 0.5) < 0.05
    return {"ok": True, "parry": PARRY, "perfect": perfect, "stun": 1.5 if perfect else 0.5}
