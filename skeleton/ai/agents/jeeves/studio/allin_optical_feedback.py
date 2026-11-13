"""All-in optical feedback scaler."""
from __future__ import annotations
from typing import Dict, Any

def feedback_allin(optical: float, rooms: int) -> Dict[str, Any]:
    if optical < 0.8 or rooms < 1:
        return {"ok": False, "reason": "floors", "difficulty": 1.0}
    difficulty = 0.7 + optical * 0.45
    salvage = 1.0 + optical * 0.25
    return {"ok": True, "difficulty": difficulty, "salvage": salvage, "rooms": rooms, "optical": optical, "reason": "ok"}
