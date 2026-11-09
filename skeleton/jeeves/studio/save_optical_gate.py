"""Optical gate for save slots."""
from __future__ import annotations
from typing import Dict, Any

def gate_save(slot: str, optical: float) -> Dict[str, Any]:
    if not slot or optical < 0.8:
        return {"ok": False, "reason": "floors", "saved": False}
    return {"ok": True, "slot": slot, "optical": optical, "saved": True, "reason": "ok"}
