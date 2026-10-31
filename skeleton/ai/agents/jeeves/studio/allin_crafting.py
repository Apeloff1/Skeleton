"""All-in optical crafting gate."""
from __future__ import annotations
from typing import Dict, Any

def craft_allin(salvage: float, optical: float) -> Dict[str, Any]:
    if salvage < 0.5 or optical < 0.8:
        return {"ok": False, "reason": "floors", "craftable": False}
    return {"ok": True, "salvage": salvage, "optical": optical, "craftable": True, "reason": "ok"}
