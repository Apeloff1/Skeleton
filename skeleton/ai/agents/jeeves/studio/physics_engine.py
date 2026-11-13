"""Advanced physics engine.
Multi-body AABB, optical mass, friction, gravity, and collision response.
"""
from typing import Any, Dict, List, Tuple

class PhysicsEngine:
    def __init__(self):
        self.bodies: Dict[str, Dict[str, Any]] = {}

    def add(self, bid: str, pos: Tuple[float, float], vel: Tuple[float, float], mass: float, optical: float) -> None:
        self.bodies[bid] = {"pos": list(pos), "vel": list(vel), "mass": mass * (1.0 + optical * 0.2), "optical": optical}

    def step(self, dt: float, gravity: float = 9.8) -> Dict[str, Any]:
        collisions = 0
        ids = list(self.bodies)
        for i, a in enumerate(ids):
            ba = self.bodies[a]
            ba["vel"][1] += gravity * dt
            ba["vel"][0] *= 0.98
            ba["vel"][1] *= 0.98
            ba["pos"][0] += ba["vel"][0] * dt
            ba["pos"][1] += ba["vel"][1] * dt
            for b in ids[i+1:]:
                bb = self.bodies[b]
                if abs(ba["pos"][0] - bb["pos"][0]) < 16 and abs(ba["pos"][1] - bb["pos"][1]) < 16:
                    collisions += 1
                    ba["vel"][0] *= -0.5
                    bb["vel"][0] *= -0.5
        return {"bodies": len(self.bodies), "collisions": collisions, "dt": dt, "schema": "skeleton.physics.v2"}
