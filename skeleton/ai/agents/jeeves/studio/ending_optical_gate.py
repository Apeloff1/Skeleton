"""Optical gate for ending."""
from __future__ import annotations
from typing import Dict, Any

def gate_ending(optical: float, salvage: float) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "floors", "ending": "fail"}
    ending = "rich" if optical > 0.92 and salvage > 0.85 else "standard"
    return {"ok": True, "ending": ending, "optical": optical, "reason": "ok"}
