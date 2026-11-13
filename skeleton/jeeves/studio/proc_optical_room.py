"""Expand procedural rooms by optical."""
from __future__ import annotations
from typing import Dict, Any

def expand_optical_rooms(base: int, optical: float) -> Dict[str, Any]:
    if base < 1 or optical < 0.8:
        return {"ok": False, "reason": "floors", "rooms": base}
    rooms = int(base * (1.0 + optical * 0.4))
    return {"ok": True, "base": base, "rooms": rooms, "optical": optical, "reason": "ok"}
