"""All-in procedural graph with optical biomes."""
from __future__ import annotations
from typing import Dict, Any, List

def graph_allin(rooms: int, optical: float, era: str) -> Dict[str, Any]:
    if rooms < 2 or optical < 0.8 or not era:
        return {"ok": False, "reason": "floors", "edges": []}
    edges = [[i, i+1] for i in range(rooms-1)]
    biomes = [f"{era}_core", f"{era}_vault"]
    return {"ok": True, "rooms": rooms, "edges": edges, "biomes": biomes, "optical": optical, "reason": "ok"}
