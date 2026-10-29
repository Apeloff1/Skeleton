"""Deep local AI loop with ratchet."""
from __future__ import annotations
from typing import Dict, Any

def loop_deep(tier: str, optical: float, fidelity: float) -> Dict[str, Any]:
    if fidelity < 0.92 or optical < 0.85:
        return {"ok": False, "reason": "floors", "next": "hold"}
    next_a = "advance" if tier == "final" else "refine"
    return {"ok": True, "tier": tier, "next": next_a, "optical": optical, "fidelity": fidelity, "reason": "ok"}
