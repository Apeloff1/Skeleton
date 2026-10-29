"""Godot scene graph emitter.
Builds Node2D/Node3D trees from room graphs.
"""
from typing import Any, Dict, List

class GodotSceneGraph:
    def emit(self, rooms: int, mode: str, era: str) -> Dict[str, Any]:
        nodes = []
        for i in range(rooms):
            node_type = "Node3D" if mode == "3d" else "Node2D"
            nodes.append({"name": f"Room_{i}", "type": node_type, "era": era})
        return {
            "root": "World",
            "nodes": nodes,
            "mode": mode,
            "schema": "skeleton.godot.scene.v1",
        }
