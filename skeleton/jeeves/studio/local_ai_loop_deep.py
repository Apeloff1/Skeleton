"""Deep local AI loop with multi-tier ratchet and optical feedback."""
from __future__ import annotations
from typing import Dict, Any

def run_deep_cycle(tier: str, optical: float, fidelity: float) -> Dict[str, Any]:
    if fidelity < 0.92 or optical < 0.85:
        return {"ok": False, "reason": "floors_failed", "next": "hold"}
    next_action = "advance" if tier == "final" else "refine"
    return {"ok": True, "tier": tier, "next": next_action, "optical": optical, "fidelity": fidelity, "reason": "ok"}
