"""Procedural generator.
Room graphs, packs, loot, and boss placement from optical and era.
"""
from typing import Any, Dict, List

class ProceduralGenerator:
    def generate(self, rooms: int, optical: float, era: str) -> Dict[str, Any]:
        graph = []
        for i in range(rooms):
            neighbors = [i - 1] if i > 0 else []
            if i < rooms - 1:
                neighbors.append(i + 1)
            graph.append({"id": i, "neighbors": neighbors, "optical": optical})
        packs = [{"room": i % rooms, "value": int(8 * (1 + optical * 0.5))} for i in range(rooms * 2)]
        boss = {"room": rooms - 1, "phase": 4, "optical": optical}
        return {
            "rooms": rooms,
            "graph": len(graph),
            "packs": len(packs),
            "boss": boss,
            "era": era,
            "optical": optical,
            "schema": "skeleton.proc.gen.v1",
        }
