"""Health bar. Player and enemy HP display data."""
from typing import Any, Dict
class HealthBar:
    def data(self, current: float, maximum: float) -> Dict[str, Any]:
        return {"current": current, "max": maximum, "percent": round(current / max(1, maximum), 2)}
