"""Ledge. Grab and pull-up."""
from typing import Any, Dict
class Ledge:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "ledge", "optical": kwargs.get("optical", 0.9)}
