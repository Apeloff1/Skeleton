"""multi_era_0002. Multi-era system.
Binds to gb era (gaming or Skeleton). Concrete run-time behavior.
"""
from typing import Any, Dict

class MultiEra0002:
    ERA = "gb"
    def run(self, optical: float = 0.9, salvage: int = 0) -> Dict[str, Any]:
        mod = 1.0 + (hash(self.ERA) % 5) * 0.01
        return {
            "ok": True,
            "system": "multi_era_0002",
            "era": self.ERA,
            "optical_mod": round(optical * mod, 3),
            "salvage_out": salvage + (2 % 15),
            "version": "v2.2",
            "gaming": self.ERA in ["nes", "snes", "gb", "gbc", "gba", "n64", "ps1", "ps2", "dreamcast", "arcade"],
        }
