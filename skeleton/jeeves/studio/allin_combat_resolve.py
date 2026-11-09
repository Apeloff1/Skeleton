"""All-in optical combat resolver."""
from __future__ import annotations
from typing import Dict, Any

def combat_allin(damage: float, armor: float, optical: float) -> Dict[str, Any]:
    if damage < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "effective": 0.0}
    effective = max(0.0, damage - armor * optical)
    return {"ok": True, "effective": effective, "optical": optical, "reason": "ok"}
