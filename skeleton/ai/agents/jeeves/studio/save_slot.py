"""Save slot.
Named slots with optical and fidelity tags.
"""
from typing import Any, Dict

class SaveSlot:
    def save(self, name: str, optical: float, fidelity: float) -> Dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            return {"ok": False, "reason": "empty_name", "schema": "skeleton.save.v1"}
        return {"ok": True, "name": name, "optical": optical, "fidelity": fidelity, "reason": "ok", "schema": "skeleton.save.v1"}
