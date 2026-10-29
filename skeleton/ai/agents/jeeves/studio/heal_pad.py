"""Heal pad. Restores health on step."""
from typing import Any, Dict
class HealPad:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "heal_pad", "optical": kwargs.get("optical", 0.9)}
