"""Consumer cache.
Simple optical-tagged cache for generated packs.
"""
from typing import Any, Dict

class ConsumerCache:
    def __init__(self):
        self.store: Dict[str, Any] = {}

    def put(self, key: str, value: Any, optical: float) -> Dict[str, Any]:
        if not isinstance(key, str) or not key.strip():
            return {"ok": False, "reason": "empty_key", "schema": "skeleton.cache.v1"}
        self.store[key] = {"value": value, "optical": optical}
        return {"ok": True, "key": key, "optical": optical, "reason": "ok", "schema": "skeleton.cache.v1"}

    def get(self, key: str) -> Dict[str, Any]:
        if key not in self.store:
            return {"ok": False, "reason": "miss", "schema": "skeleton.cache.v1"}
        return {"ok": True, "key": key, "value": self.store[key]["value"], "optical": self.store[key]["optical"], "reason": "ok", "schema": "skeleton.cache.v1"}
