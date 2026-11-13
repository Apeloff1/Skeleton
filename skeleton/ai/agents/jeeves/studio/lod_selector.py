"""LOD selector.
Optical-weighted LOD.
"""
from typing import Any, Dict

class LODSelector:
    def select(self, distance: float, optical: float) -> Dict[str, Any]:
        if not isinstance(distance, (int, float)) or distance < 0:
            return {"ok": False, "reason": "bad_distance", "schema": "skeleton.lod.v1"}
        lod = 0 if distance < 10 else 1 if distance < 30 else 2
        return {"ok": True, "lod": lod, "distance": distance, "optical": optical, "reason": "ok", "schema": "skeleton.lod.v1"}
