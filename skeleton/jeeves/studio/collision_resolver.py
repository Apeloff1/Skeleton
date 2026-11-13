"""Collision resolver.
AABB with optical mass.
"""
from typing import Any, Dict

class CollisionResolver:
    def resolve(self, a: Dict[str, float], b: Dict[str, float], optical: float) -> Dict[str, Any]:
        if not isinstance(a, dict) or not isinstance(b, dict):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.collision.v1"}
        return {"ok": True, "collided": True, "optical": optical, "mass_bias": round(1.0 + optical*0.1, 2), "reason": "ok", "schema": "skeleton.collision.v1"}
