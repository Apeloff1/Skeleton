"""Build Godot scene graph with era and mode nodes."""
from __future__ import annotations
from typing import Dict, Any, List

def build_graph(era: str, mode: str, rooms: int) -> Dict[str, Any]:
    if rooms < 1:
        return {"ok": False, "reason": "bad_rooms", "nodes": []}
    nodes = ["World", "Player", "Boss", "Cutscene"] + [f"Room_{i}" for i in range(rooms)]
    return {"ok": True, "root": "World", "nodes": nodes, "era": era, "mode": mode, "reason": "ok"}
