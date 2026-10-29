"""Turret base. Placeable defense."""
from typing import Any, Dict
class TurretBase:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "turret_base", "optical": kwargs.get("optical", 0.9)}
