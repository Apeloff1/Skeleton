"""Ammo crate. Refills ammo."""
from typing import Any, Dict
class AmmoCrate:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "ammo_crate", "optical": kwargs.get("optical", 0.9)}
