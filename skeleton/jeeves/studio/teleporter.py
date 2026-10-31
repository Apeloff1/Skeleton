"""Teleporter. Instant room jump."""
from typing import Any, Dict
class Teleporter:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "teleporter", "optical": kwargs.get("optical", 0.9)}
