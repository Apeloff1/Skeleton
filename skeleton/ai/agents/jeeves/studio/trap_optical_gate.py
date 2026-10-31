"""Optical gate for traps."""
from __future__ import annotations
from typing import Dict, Any

def gate_trap(optical: float) -> Dict[str, Any]:
    if optical < 0.7:
        return {"ok": False, "reason": "floors", "damage": 0.0}
    damage = 10.0 * (1.1 - optical * 0.2)
    return {"ok": True, "damage": damage, "optical": optical, "reason": "ok"}
