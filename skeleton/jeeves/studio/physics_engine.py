"""Advanced physics engine.
AABB collision, velocity integration, friction, gravity, and optical mass bias.
"""
from typing import Any, Dict, List, Tuple

class PhysicsEngine:
    def __init__(self):
        self.bodies: Dict[str, Dict[str, Any]] = {}

    def add(self, bid: str, pos: Tuple[float, float], vel: Tuple[float, float], mass: float, optical: float) -> None:
        self.bodies[bid] = {"pos": list(pos), "vel": list(vel), "mass": mass * (1.0 + optical * 0.2)}

    def step(self, dt: float, gravity: float = 9.8) -> Dict[str, Any]:
        for b in self.bodies.values():
            b["vel"][1] += gravity * dt
            b["vel"][0] *= 0.98
            b["vel"][1] *= 0.98
            b["pos"][0] += b["vel"][0] * dt
            b["pos"][1] += b["vel"][1] * dt
        return {"bodies": len(self.bodies), "dt": dt, "schema": "skeleton.physics.v1"}

    def collide(self, a: str, b: str) -> bool:
        if a not in self.bodies or b not in self.bodies:
            return False
        pa, pb = self.bodies[a]["pos"], self.bodies[b]["pos"]
        return abs(pa[0] - pb[0]) < 16 and abs(pa[1] - pb[1]) < 16
