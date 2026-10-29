"""Check multi-tier optical floors."""
from __future__ import annotations
from typing import Dict, Any

def check_floors(optical: float, tier: str) -> Dict[str, Any]:
    floors = {"draft": 0.85, "refine": 0.90, "final": 0.92}
    floor = floors.get(tier, 0.92)
    if optical < floor:
        return {"ok": False, "reason": "below_floor", "tier": tier}
    return {"ok": True, "tier": tier, "optical": optical, "floor": floor, "reason": "ok"}
