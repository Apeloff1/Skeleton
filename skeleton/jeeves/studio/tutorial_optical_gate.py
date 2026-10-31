"""Optical gate for tutorial."""
from __future__ import annotations
from typing import Dict, Any

def gate_tutorial(step: int, optical: float) -> Dict[str, Any]:
    if step < 0 or optical < 0.75:
        return {"ok": False, "reason": "floors", "advance": False}
    advance = optical > 0.85
    return {"ok": True, "step": step, "advance": advance, "optical": optical, "reason": "ok"}
