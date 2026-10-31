"""Scale optical feedback params."""
from __future__ import annotations
from typing import Dict, Any

def scale_feedback(optical: float, rooms: int) -> Dict[str, Any]:
    if optical < 0.8 or rooms < 1:
        return {"ok": False, "reason": "floors", "difficulty": 1.0}
    difficulty = 0.7 + optical * 0.5
    return {"ok": True, "difficulty": difficulty, "rooms": rooms, "optical": optical, "reason": "ok"}
