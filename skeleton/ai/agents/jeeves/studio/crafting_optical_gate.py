"""Optical gate for crafting."""
from __future__ import annotations
from typing import Dict, Any

def gate_craft(salvage: float, optical: float) -> Dict[str, Any]:
    if salvage < 0.4 or optical < 0.8:
        return {"ok": False, "reason": "floors", "crafted": False}
    return {"ok": True, "salvage": salvage, "optical": optical, "crafted": True, "reason": "ok"}
