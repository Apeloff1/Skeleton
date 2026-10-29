"""Resolve combat with optical damage."""
from __future__ import annotations
from typing import Dict, Any

def resolve_optical(damage: float, optical: float) -> Dict[str, Any]:
    if damage < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "effective": 0.0}
    effective = damage * optical
    return {"ok": True, "damage": damage, "effective": effective, "optical": optical, "reason": "ok"}
