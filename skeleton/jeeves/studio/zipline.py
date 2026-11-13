"""Zipline. Fast travel between points."""
from typing import Any, Dict
class Zipline:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "zipline", "optical": kwargs.get("optical", 0.9)}
