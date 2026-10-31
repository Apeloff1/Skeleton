"""Optical gate for checkpoint."""
from __future__ import annotations
from typing import Dict, Any

def gate_checkpoint(id: str, optical: float) -> Dict[str, Any]:
    if not id or optical < 0.8:
        return {"ok": False, "reason": "floors", "set": False}
    return {"ok": True, "id": id, "optical": optical, "set": True, "reason": "ok"}
