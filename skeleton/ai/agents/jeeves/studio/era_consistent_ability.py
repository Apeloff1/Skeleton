"""Return era-consistent abilities."""
from __future__ import annotations
from typing import Dict, Any, List

def get_abilities(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "abilities": []}
    abilities = ["move", "interact", "salvage"]
    if era in ("NES", "SNES", "GBA", "N64"):
        abilities.extend(["jump", "shoot"])
    if era in ("ash", "crystal", "void", "rift"):
        abilities.append("optical_attune")
    return {"ok": True, "era": era, "abilities": abilities, "reason": "ok"}
