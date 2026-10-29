"""Place procedural boss by optical."""
from __future__ import annotations
from typing import Dict, Any

def place_boss(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 1 or optical < 0.8:
        return {"ok": False, "reason": "floors", "placed": False}
    room = rooms - 1 if optical > 0.85 else rooms // 2
    return {"ok": True, "room": room, "optical": optical, "placed": True, "reason": "ok"}
