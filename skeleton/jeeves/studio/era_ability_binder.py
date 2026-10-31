"""Bind era-consistent abilities with optical scale."""
from __future__ import annotations
from typing import Dict, Any, List

def bind_abilities(era: str, optical: float) -> Dict[str, Any]:
    if not era or optical < 0.8:
        return {"ok": False, "reason": "floors", "abilities": []}
    base = ["move", "interact", "salvage"]
    if era in ("NES", "SNES", "GBA"):
        base.extend(["jump", "shoot"])
    if era in ("ash", "crystal", "void"):
        base.append("optical_attune")
    return {"ok": True, "era": era, "abilities": base, "optical": optical, "reason": "ok"}
