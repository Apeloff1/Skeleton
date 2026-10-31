"""Update faction standing by optical."""
from __future__ import annotations
from typing import Dict, Any

def update_standing(faction: str, optical: float) -> Dict[str, Any]:
    if not faction or optical < 0.75:
        return {"ok": False, "reason": "floors", "standing": 0.0}
    standing = optical * 100
    return {"ok": True, "faction": faction, "standing": standing, "optical": optical, "reason": "ok"}
