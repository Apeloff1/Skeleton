"""Trap trigger. Activation condition."""
from typing import Any, Dict
class TrapTrigger:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "trap_trigger", "optical": kwargs.get("optical", 0.9)}
