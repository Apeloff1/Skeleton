"""Roll loot value with optical."""
from __future__ import annotations
from typing import Dict, Any

def roll_value(base: int, optical: float) -> Dict[str, Any]:
    if base < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "value": 0}
    value = int(base * (0.8 + optical * 0.5))
    return {"ok": True, "base": base, "value": value, "optical": optical, "reason": "ok"}
