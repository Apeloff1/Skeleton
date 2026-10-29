"""era_system_013. Multi-era system.
Binds to rift era. Provides concrete run-time behavior.
"""
from typing import Any, Dict

class EraSystem013:
    ERA = "rift"
    def run(self, optical: float = 0.9, salvage: int = 0) -> Dict[str, Any]:
        return {
            "ok": True,
            "system": "era_system_013",
            "era": self.ERA,
            "optical_mod": round(optical * (1.0 + (13 % 5) * 0.02), 3),
            "salvage_out": salvage + (13 % 10),
            "version": "v1.3",
        }
