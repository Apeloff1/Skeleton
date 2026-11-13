"""Decoy. Draws aggro temporarily."""
from typing import Any, Dict
class Decoy:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "decoy", "optical": kwargs.get("optical", 0.9)}
