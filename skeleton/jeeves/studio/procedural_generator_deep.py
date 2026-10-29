"""Deep procedural generator."""
from __future__ import annotations
from typing import Dict, Any

def generate_deep(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 1 or optical < 0.8:
        return {"ok": False, "reason": "floors", "generated": False}
    return {"ok": True, "rooms": rooms, "optical": optical, "generated": True, "reason": "ok"}
