"""era_system_010. Multi-era system.
Binds to ash era. Provides concrete run-time behavior.
"""
from typing import Any, Dict

class EraSystem010:
    ERA = "ash"
    def run(self, optical: float = 0.9, salvage: int = 0) -> Dict[str, Any]:
        return {
            "ok": True,
            "system": "era_system_010",
            "era": self.ERA,
            "optical_mod": round(optical * (1.0 + (10 % 5) * 0.02), 3),
            "salvage_out": salvage + (10 % 10),
            "version": "v1.0",
        }
