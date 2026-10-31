"""Resolve narrative ending from optical and salvage."""
from __future__ import annotations
from typing import Dict, Any

def resolve_ending(optical: float, salvage: int) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "optical_floor", "ending": "fail"}
    ending = "extract_rich" if salvage > 30 else "extract_base"
    return {"ok": True, "ending": ending, "optical": optical, "salvage": salvage, "reason": "ok"}
