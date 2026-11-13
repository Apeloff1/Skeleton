"""Level graph.
Multi-room graph with optical density and era tags.
"""
from typing import Any, Dict, List

class LevelGraph:
    def build(self, rooms: int, optical: float, era: str) -> Dict[str, Any]:
        if not isinstance(rooms, int) or rooms < 1:
            return {"ok": False, "reason": "bad_rooms", "schema": "skeleton.level.graph.v1"}
        nodes = [{"id": i, "era": era, "optical": optical} for i in range(rooms)]
        edges = [[i, i+1] for i in range(rooms-1)]
        return {"ok": True, "nodes": nodes, "edges": edges, "rooms": rooms, "era": era, "optical": optical, "reason": "ok", "schema": "skeleton.level.graph.v1"}
