"""All-in era-consistent abilities."""
from __future__ import annotations
from typing import Dict, Any, List

def ability_allin(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "abilities": []}
    abilities = ["move", "interact", "salvage"]
    if era in ("NES", "SNES", "GBA", "N64", "PS1", "PS2"):
        abilities.extend(["jump", "shoot"])
    if era in ("ash", "crystal", "void", "rift", "core"):
        abilities.append("optical_attune")
    return {"ok": True, "era": era, "abilities": abilities, "reason": "ok"}
