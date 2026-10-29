"""Optical gate for map reveal."""
from __future__ import annotations
from typing import Dict, Any

def gate_map(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 1 or optical < 0.8:
        return {"ok": False, "reason": "floors", "revealed": 0}
    revealed = int(rooms * optical)
    return {"ok": True, "revealed": revealed, "optical": optical, "reason": "ok"}
