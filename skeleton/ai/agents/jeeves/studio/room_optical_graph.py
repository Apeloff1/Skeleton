"""Build optical-biased room graph."""
from __future__ import annotations
from typing import Dict, Any, List

def build_graph(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 2 or optical < 0.8:
        return {"ok": False, "reason": "floors", "edges": []}
    edges = [[i, i+1] for i in range(rooms-1)]
    if optical > 0.92:
        edges.append([0, rooms-1])
    return {"ok": True, "rooms": rooms, "edges": edges, "optical": optical, "reason": "ok"}
