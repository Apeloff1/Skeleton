"""Energy barrier. Damage on contact."""
from typing import Any, Dict
class EnergyBarrier:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "energy_barrier", "optical": kwargs.get("optical", 0.9)}
