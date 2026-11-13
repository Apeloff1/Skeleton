"""era_system_008. Multi-era system.
Binds to rift era. Provides concrete run-time behavior.
"""
from typing import Any, Dict

class EraSystem008:
    ERA = "rift"
    def run(self, optical: float = 0.9, salvage: int = 0) -> Dict[str, Any]:
        return {
            "ok": True,
            "system": "era_system_008",
            "era": self.ERA,
            "optical_mod": round(optical * (1.0 + (8 % 5) * 0.02), 3),
            "salvage_out": salvage + (8 % 10),
            "version": "v1.8",
        }
