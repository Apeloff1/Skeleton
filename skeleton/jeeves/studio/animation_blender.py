"""Animation blender.
Optical-weighted blend between clips.
"""
from typing import Any, Dict

class AnimationBlender:
    def blend(self, a: str, b: str, optical: float) -> Dict[str, Any]:
        if not isinstance(a, str) or not isinstance(b, str):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.anim.blend.v1"}
        t = round(optical, 2)
        return {"ok": True, "from": a, "to": b, "t": t, "optical": optical, "reason": "ok", "schema": "skeleton.anim.blend.v1"}
