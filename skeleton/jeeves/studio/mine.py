"""Mine. Proximity explosive."""
from typing import Any, Dict
class Mine:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "mine", "optical": kwargs.get("optical", 0.9)}
