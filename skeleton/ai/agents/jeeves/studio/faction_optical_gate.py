"""Optical gate for faction."""
from __future__ import annotations
from typing import Dict, Any

def gate_faction(optical: float) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "floors", "tier": "neutral"}
    tier = "ally" if optical > 0.92 else "friendly" if optical > 0.85 else "neutral"
    return {"ok": True, "tier": tier, "optical": optical, "reason": "ok"}
