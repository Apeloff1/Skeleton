"""All-in AI cycle across tiers with ratchet."""
from __future__ import annotations
from typing import Dict, Any

def cycle_allin(tier: str, optical: float, fidelity: float) -> Dict[str, Any]:
    if tier not in ("draft", "refine", "final") or optical < 0.85 or fidelity < 0.92:
        return {"ok": False, "reason": "floors", "next": "hold"}
    next_t = "refine" if tier == "draft" else "final" if tier == "refine" else "final"
    return {"ok": True, "tier": tier, "next": next_t, "optical": optical, "fidelity": fidelity, "reason": "ok"}
