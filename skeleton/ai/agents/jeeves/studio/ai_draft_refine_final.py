"""Run draft/refine/final with optical."""
from __future__ import annotations
from typing import Dict, Any

def run_tiers(optical: float) -> Dict[str, Any]:
    if optical < 0.85:
        return {"ok": False, "reason": "floors", "tiers": []}
    tiers = ["draft", "refine", "final"]
    return {"ok": True, "tiers": tiers, "optical": optical, "reason": "ok"}
