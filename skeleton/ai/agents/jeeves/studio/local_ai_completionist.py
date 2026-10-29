"""Completionist local AI: full draft/refine/final with optical floors and ratchet lock."""
from __future__ import annotations
from typing import Dict, Any, List

def run_completionist_ai(brief: str, optical: float = 0.95, fidelity: float = 0.96) -> Dict[str, Any]:
    if not brief or optical < 0.9 or fidelity < 0.92:
        return {"ok": False, "reason": "floors_failed", "tier": "none", "sealed": False}
    tiers = ["draft", "refine", "final"]
    current = "final" if fidelity >= 0.94 else "refine"
    high_water = max(fidelity, 0.94)
    locked = high_water >= 0.95
    return {
        "ok": True,
        "reason": "ok",
        "brief": brief,
        "tier": current,
        "tiers": tiers,
        "optical": optical,
        "fidelity": fidelity,
        "high_water": high_water,
        "locked": locked,
        "sealed": locked,
        "modules": ["decomp_weights", "optical_feedback", "ratchet", "export_gate"],
    }
