"""Slow field. Movement reduction."""
from typing import Any, Dict
class SlowField:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "slow_field", "optical": kwargs.get("optical", 0.9)}
