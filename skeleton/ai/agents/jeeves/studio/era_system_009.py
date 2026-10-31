"""era_system_009. Multi-era system.
Binds to core era. Provides concrete run-time behavior.
"""
from typing import Any, Dict

class EraSystem009:
    ERA = "core"
    def run(self, optical: float = 0.9, salvage: int = 0) -> Dict[str, Any]:
        return {
            "ok": True,
            "system": "era_system_009",
            "era": self.ERA,
            "optical_mod": round(optical * (1.0 + (9 % 5) * 0.02), 3),
            "salvage_out": salvage + (9 % 10),
            "version": "v1.9",
        }
