"""Load manager.
Named slots with optical and fidelity.
"""
from typing import Any, Dict

class LoadManager:
    def load(self, name: str) -> Dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            return {"ok": False, "reason": "empty_name", "schema": "skeleton.load.mgr.v1"}
        return {"ok": True, "name": name, "optical": 0.95, "fidelity": 0.94, "reason": "ok", "schema": "skeleton.load.mgr.v1"}
