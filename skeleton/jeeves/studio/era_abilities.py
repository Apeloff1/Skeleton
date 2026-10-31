"""Era abilities.
Multi-era ability sets with optical attune.
"""
from typing import Any, Dict, List

class EraAbilities:
    def set(self, era: str, optical: float) -> Dict[str, Any]:
        base = ["move", "interact", "salvage"]
        if era in ["nes", "snes", "gb", "gbc", "gba"]:
            base += ["jump", "shoot"]
        if era in ["ash", "crystal", "void"]:
            base += ["optical_attune", "phase_shift"]
        return {"ok": True, "era": era, "abilities": base, "optical": optical, "reason": "ok", "schema": "skeleton.era.abilities.v1"}
