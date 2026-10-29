"""Expand era abilities with optical bias."""
from __future__ import annotations
from typing import Dict, Any, List

def expand_abilities(era: str, optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "optical_floor", "abilities": []}
    base = ["move", "interact", "salvage"]
    if era in ("ash", "crystal"):
        base.append("optical_attune")
    if optical > 0.9:
        base.append("phase_shift")
    return {"ok": True, "era": era, "abilities": base, "reason": "ok"}
