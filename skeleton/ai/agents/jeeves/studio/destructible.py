"""Destructible. Breakable cover or object."""
from typing import Any, Dict
class Destructible:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "destructible", "optical": kwargs.get("optical", 0.9)}
