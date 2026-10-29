"""Frustum cull.
Optical-weighted culling.
"""
from typing import Any, Dict

class FrustumCull:
    def cull(self, count: int, optical: float) -> Dict[str, Any]:
        if not isinstance(count, int) or count < 0:
            return {"ok": False, "reason": "bad_count", "schema": "skeleton.cull.v1"}
        visible = int(count * (0.5 + optical*0.5))
        return {"ok": True, "total": count, "visible": visible, "culled": count - visible, "optical": optical, "reason": "ok", "schema": "skeleton.cull.v1"}
