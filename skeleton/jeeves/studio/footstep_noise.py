"""Footstep noise. Movement audio radius."""
from typing import Any, Dict
class FootstepNoise:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "footstep_noise", "optical": kwargs.get("optical", 0.9)}
