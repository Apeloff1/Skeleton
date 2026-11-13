"""era_system_006. Multi-era system.
Binds to crystal era. Provides concrete run-time behavior.
"""
from typing import Any, Dict

class EraSystem006:
    ERA = "crystal"
    def run(self, optical: float = 0.9, salvage: int = 0) -> Dict[str, Any]:
        return {
            "ok": True,
            "system": "era_system_006",
            "era": self.ERA,
            "optical_mod": round(optical * (1.0 + (6 % 5) * 0.02), 3),
            "salvage_out": salvage + (6 % 10),
            "version": "v1.6",
        }
