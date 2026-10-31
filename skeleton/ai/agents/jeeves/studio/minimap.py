"""Minimap. Revealed room overview."""
from typing import Any, Dict, List
class Minimap:
    def render(self, revealed: List[int], current: int) -> Dict[str, Any]:
        return {"revealed": revealed, "current": current, "count": len(revealed)}
