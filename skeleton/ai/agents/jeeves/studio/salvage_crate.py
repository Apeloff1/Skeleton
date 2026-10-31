"""Salvage crate. Extra salvage drop."""
from typing import Any, Dict
class SalvageCrate:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "salvage_crate", "optical": kwargs.get("optical", 0.9)}
