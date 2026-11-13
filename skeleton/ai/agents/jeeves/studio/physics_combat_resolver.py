"""Resolve combat with physics impulse and optical mass."""
from __future__ import annotations
from typing import Dict, Any

def resolve_hit(damage: float, armor: float, optical: float) -> Dict[str, Any]:
    if damage < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "knockback": 0.0}
    effective = max(0.0, damage - armor * optical)
    knockback = effective * 0.2 * optical
    return {"ok": True, "effective": effective, "knockback": knockback, "optical": optical, "reason": "ok"}
