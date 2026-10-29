"""Consumer config.
End-user settings with optical and fidelity floors.
"""
from typing import Any, Dict

class ConsumerConfig:
    def load(self, optical: float = 0.95, fidelity: float = 0.94) -> Dict[str, Any]:
        if not isinstance(optical, (int, float)) or not isinstance(fidelity, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.config.v1"}
        return {"ok": True, "optical": optical, "fidelity": fidelity, "floors": {"optical": 0.9, "fidelity": 0.92}, "reason": "ok", "schema": "skeleton.config.v1"}
