"""Tag save slot with optical."""
from __future__ import annotations
from typing import Dict, Any

def tag_optical(slot: str, optical: float) -> Dict[str, Any]:
    if not slot or optical < 0.8:
        return {"ok": False, "reason": "floors", "tagged": False}
    return {"ok": True, "slot": slot, "optical": optical, "tagged": True, "reason": "ok"}
