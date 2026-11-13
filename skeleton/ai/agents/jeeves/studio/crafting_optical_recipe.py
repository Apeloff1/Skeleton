"""Gate crafting recipe by optical."""
from __future__ import annotations
from typing import Dict, Any

def gate_recipe(salvage: float, optical: float) -> Dict[str, Any]:
    if salvage < 0.5 or optical < 0.8:
        return {"ok": False, "reason": "floors", "craftable": False}
    return {"ok": True, "salvage": salvage, "optical": optical, "craftable": True, "reason": "ok"}
