"""All-in Godot scene graph builder."""
from __future__ import annotations
from typing import Dict, Any, List

def graph_allin_scene(rooms: int, era: str) -> Dict[str, Any]:
    if rooms < 1 or not era:
        return {"ok": False, "reason": "floors", "nodes": []}
    nodes = ["World", "Player"] + [f"Room_{i}" for i in range(rooms)] + ["Boss", "Cutscene"]
    return {"ok": True, "nodes": nodes, "era": era, "rooms": rooms, "reason": "ok"}
