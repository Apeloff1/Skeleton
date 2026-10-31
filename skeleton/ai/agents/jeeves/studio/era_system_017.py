"""era_system_017. Multi-era system.
Binds to void era. Provides concrete run-time behavior.
"""
from typing import Any, Dict

class EraSystem017:
    ERA = "void"
    def run(self, optical: float = 0.9, salvage: int = 0) -> Dict[str, Any]:
        return {
            "ok": True,
            "system": "era_system_017",
            "era": self.ERA,
            "optical_mod": round(optical * (1.0 + (17 % 5) * 0.02), 3),
            "salvage_out": salvage + (17 % 10),
            "version": "v1.7",
        }
