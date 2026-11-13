"""Optical-tagged save slots."""
from __future__ import annotations
from typing import Dict, Any

def tag_save(slot: str, optical: float, fidelity: float) -> Dict[str, Any]:
    if not slot or optical < 0.8 or fidelity < 0.9:
        return {"ok": False, "reason": "floors", "tagged": False}
    return {"ok": True, "slot": slot, "optical": optical, "fidelity": fidelity, "tagged": True, "reason": "ok"}
