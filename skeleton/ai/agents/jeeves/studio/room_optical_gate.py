"""Optical gate for room connector."""
from __future__ import annotations
from typing import Dict, Any, List

def gate_room(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 2 or optical < 0.8:
        return {"ok": False, "reason": "floors", "edges": []}
    edges = [[i, i+1] for i in range(rooms-1)]
    return {"ok": True, "edges": edges, "optical": optical, "reason": "ok"}
