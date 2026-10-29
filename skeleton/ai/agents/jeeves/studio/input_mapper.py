"""Input mapper.
Optical-biased input.
"""
from typing import Any, Dict

class InputMapper:
    def map(self, action: str, optical: float) -> Dict[str, Any]:
        if not isinstance(action, str) or not action.strip():
            return {"ok": False, "reason": "empty_action", "schema": "skeleton.input.map.v1"}
        return {"ok": True, "action": action, "optical": optical, "bias": round(optical, 2), "reason": "ok", "schema": "skeleton.input.map.v1"}
