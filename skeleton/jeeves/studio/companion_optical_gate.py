"""Optical gate for companion."""
from __future__ import annotations
from typing import Dict, Any

def gate_companion(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "mode": "idle"}
    mode = "scout" if optical > 0.9 else "assist"
    return {"ok": True, "mode": mode, "optical": optical, "reason": "ok"}
