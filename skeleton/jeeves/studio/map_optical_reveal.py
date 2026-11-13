"""Reveal map by optical."""
from __future__ import annotations
from typing import Dict, Any

def reveal_map(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 1 or optical < 0.8:
        return {"ok": False, "reason": "floors", "revealed": 0}
    revealed = int(rooms * optical)
    return {"ok": True, "rooms": rooms, "revealed": revealed, "optical": optical, "reason": "ok"}
