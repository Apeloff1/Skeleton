"""Portal pair. Linked entry and exit."""
from typing import Any, Dict
class PortalPair:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "portal_pair", "optical": kwargs.get("optical", 0.9)}
