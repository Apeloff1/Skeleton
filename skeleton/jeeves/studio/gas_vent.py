"""Gas vent. Area debuff hazard."""
from typing import Any, Dict
class GasVent:
    def run(self, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "system": "gas_vent", "optical": kwargs.get("optical", 0.9)}
