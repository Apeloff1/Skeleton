"""Dodge. I-frames and direction."""
from typing import Any, Dict
class Dodge:
    def perform(self, direction: tuple) -> Dict[str, Any]:
        return {"direction": direction, "iframes": 0.4, "cost": 15.0}
