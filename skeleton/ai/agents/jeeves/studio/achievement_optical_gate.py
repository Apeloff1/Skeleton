"""Optical gate for achievements."""
from __future__ import annotations
from typing import Dict, Any, List

def gate_achievement(optical: float, packs: int) -> Dict[str, Any]:
    if optical < 0.8 or packs < 0:
        return {"ok": False, "reason": "floors", "unlocked": []}
    unlocked = ["starter"] if packs > 0 else []
    if optical > 0.9:
        unlocked.append("optical_ace")
    return {"ok": True, "unlocked": unlocked, "optical": optical, "reason": "ok"}
