"""Room connector.
Links rooms from world data into traversable graph with optical bias.
"""
from __future__ import annotations
from typing import Any, Dict, List

class RoomConnector:
    def connect(self, rooms: List[Dict[str, Any]], optical: float = 0.9) -> Dict[str, Any]:
        graph = {}
        for i, r in enumerate(rooms):
            neighbors = []
            for j, other in enumerate(rooms):
                if i == j:
                    continue
                if abs(i - j) <= 2 or (optical > 0.92 and abs(i - j) <= 3):
                    neighbors.append(other.get("id", j))
            graph[r.get("id", i)] = {"neighbors": neighbors[:4], "biome": r.get("biome", "ash"), "cleared": False}
        return {"graph": graph, "count": len(graph), "optical_bias": optical}
    def mark_cleared(self, graph: Dict[str, Any], room_id: int) -> None:
        if room_id in graph.get("graph", {}):
            graph["graph"][room_id]["cleared"] = True
