"""Connect biomes in procedural graph."""
from __future__ import annotations
from typing import Dict, Any, List

def connect_biomes(biomes: List[str], optical: float) -> Dict[str, Any]:
    if not biomes or optical < 0.8:
        return {"ok": False, "reason": "floors", "edges": []}
    edges = [[i, i+1] for i in range(len(biomes)-1)]
    return {"ok": True, "biomes": biomes, "edges": edges, "optical": optical, "reason": "ok"}
