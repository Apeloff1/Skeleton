"""Deep optical feedback scales difficulty, loot, and boss from fidelity."""
from __future__ import annotations
from typing import Dict, Any

def scale_params(optical: float, rooms: int) -> Dict[str, Any]:
    if optical < 0.8 or rooms < 1:
        return {"ok": False, "reason": "floors", "difficulty": 1.0}
    difficulty = 0.8 + optical * 0.4
    salvage = 1.0 + optical * 0.3
    return {"ok": True, "difficulty": difficulty, "salvage": salvage, "rooms": rooms, "optical": optical, "reason": "ok"}
