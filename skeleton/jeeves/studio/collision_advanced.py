"""Advanced collision.
AABB and optical-softened response.
"""
from typing import Any, Dict, Tuple

class CollisionAdvanced:
    def aabb(self, a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by

    def resolve(self, overlap: float, optical: float) -> float:
        return overlap * (1.0 - optical * 0.3)
