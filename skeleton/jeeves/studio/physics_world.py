"""Physics world.
Spawns rigid bodies, static colliders, and optical density fields.
"""
from typing import Any, Dict, List

class PhysicsWorld:
    def generate(self, rooms: int, optical: float, era: str) -> Dict[str, Any]:
        bodies = []
        for i in range(rooms):
            bodies.append({"id": f"room_{i}", "static": True, "optical": optical})
        bodies.append({"id": "player", "static": False, "mass": 80 * (1.0 + optical * 0.1)})
        return {
            "rooms": rooms,
            "bodies": len(bodies),
            "era": era,
            "optical": optical,
            "schema": "skeleton.physics.world.v1",
        }
