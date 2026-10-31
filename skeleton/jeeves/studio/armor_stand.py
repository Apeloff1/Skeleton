"""Armor stand. Equip armor piece."""
from typing import Any, Dict
class ArmorStand:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "armor_stand", "optical": kwargs.get("optical", 0.9)}
