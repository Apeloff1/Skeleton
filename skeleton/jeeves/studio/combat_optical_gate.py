"""Optical gate for combat."""
from __future__ import annotations
from typing import Dict, Any

def gate_combat(damage: float, optical: float) -> Dict[str, Any]:
    if damage < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "effective": 0.0}
    effective = damage * (0.9 + optical * 0.2)
    return {"ok": True, "effective": effective, "optical": optical, "reason": "ok"}
