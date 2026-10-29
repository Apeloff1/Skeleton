"""Climbable. Vertical traversal points."""
from typing import Any, Dict
class Climbable:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "climbable", "optical": kwargs.get("optical", 0.9)}
