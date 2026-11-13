"""Physics step.
Multi-body integration with optical mass.
"""
from typing import Any, Dict

class PhysicsStep:
    def integrate(self, bodies: int, dt: float, optical: float) -> Dict[str, Any]:
        if not isinstance(bodies, int) or bodies < 1 or not isinstance(dt, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.physics.step.v1"}
        return {"ok": True, "bodies": bodies, "dt": dt, "optical": optical, "mass_bias": round(1.0 + optical*0.1, 2), "reason": "ok", "schema": "skeleton.physics.step.v1"}
