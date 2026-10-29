"""Expand procedural room graph with era biomes."""
from __future__ import annotations
from typing import Dict, Any, List

def expand_graph(rooms: int, era: str, optical: float) -> Dict[str, Any]:
    if rooms < 2 or optical < 0.8:
        return {"ok": False, "reason": "floors", "graph": []}
    edges = [[i, i+1] for i in range(rooms-1)]
    biomes = [f"{era}_tunnel", f"{era}_vault"]
    return {"ok": True, "rooms": rooms, "edges": edges, "biomes": biomes, "optical": optical, "reason": "ok"}
