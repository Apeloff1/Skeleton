"""Optical-driven narrative branch."""
from __future__ import annotations
from typing import Dict, Any

def branch_optical(optical: float, salvage: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "ending": "failure"}
    ending = "rich" if optical > 0.92 and salvage > 0.85 else "high" if optical > 0.88 else "standard"
    return {"ok": True, "ending": ending, "optical": optical, "salvage": salvage, "reason": "ok"}
