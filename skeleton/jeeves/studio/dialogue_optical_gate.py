"""Optical gate for dialogue selection."""
from __future__ import annotations
from typing import Dict, Any

def gate_dialogue(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "line": "default"}
    line = "rich" if optical > 0.92 else "high" if optical > 0.85 else "standard"
    return {"ok": True, "line": line, "optical": optical, "reason": "ok"}
