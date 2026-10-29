"""Footstep 0024.
"""
from __future__ import annotations

STEP = "step_0024"

def cue(surface: str) -> dict:
    if not surface:
        return {"ok": False, "reason": "no_surface"}
    return {"ok": True, "step": STEP, "surface": surface, "volume": 0.4}
