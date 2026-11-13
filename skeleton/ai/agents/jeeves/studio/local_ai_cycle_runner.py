"""Run full local AI cycle across tiers."""
from __future__ import annotations
from typing import Dict, Any

def run_cycle(tier: str, optical: float) -> Dict[str, Any]:
    if tier not in ("draft", "refine", "final") or optical < 0.8:
        return {"ok": False, "reason": "floors", "advanced": False}
    next_tier = "refine" if tier == "draft" else "final" if tier == "refine" else "final"
    return {"ok": True, "tier": tier, "next": next_tier, "optical": optical, "advanced": True, "reason": "ok"}
