"""Ratchet local AI tiers with fidelity floor."""
from __future__ import annotations
from typing import Dict, Any

def ratchet_tier(current: str, fidelity: float) -> Dict[str, Any]:
    if fidelity < 0.92:
        return {"ok": False, "reason": "fidelity_floor", "tier": current}
    next_tier = "final" if current == "refine" else "refine" if current == "draft" else current
    return {"ok": True, "tier": next_tier, "fidelity": fidelity, "locked": True, "reason": "ok"}
