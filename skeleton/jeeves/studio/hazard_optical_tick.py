"""Tick environmental hazard with optical."""
from __future__ import annotations
from typing import Dict, Any

def tick_hazard(damage: float, optical: float) -> Dict[str, Any]:
    if damage < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "applied": 0.0}
    applied = damage * (1.1 - optical * 0.2)
    return {"ok": True, "damage": damage, "applied": applied, "optical": optical, "reason": "ok"}
