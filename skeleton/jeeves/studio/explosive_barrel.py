"""Explosive barrel. Area damage on hit."""
from typing import Any, Dict
class ExplosiveBarrel:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "explosive_barrel", "optical": kwargs.get("optical", 0.9)}
