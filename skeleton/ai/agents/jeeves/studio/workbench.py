"""Workbench. Crafting station."""
from typing import Any, Dict
class Workbench:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "workbench", "optical": kwargs.get("optical", 0.9)}
