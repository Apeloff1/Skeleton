"""Player script.
Optical-tagged player.gd with movement.
"""
from typing import Any, Dict

class PlayerScript:
    def emit(self, optical: float) -> Dict[str, Any]:
        if not isinstance(optical, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.player.script.v1"}
        text = f"var optical = {optical}\\nfunc _physics_process(delta):\\n\\tposition.x += 10 * delta"
        return {"ok": True, "optical": optical, "text": text, "reason": "ok", "schema": "skeleton.player.script.v1"}
