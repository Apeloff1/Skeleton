"""Light level. Optical visibility modifier."""
from typing import Any, Dict
class LightLevel:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "light_level", "optical": kwargs.get("optical", 0.9)}
