"""Advance tutorial step by optical."""
from __future__ import annotations
from typing import Dict, Any

def advance_step(step: int, optical: float) -> Dict[str, Any]:
    if step < 0 or optical < 0.75:
        return {"ok": False, "reason": "floors", "next": step}
    next_step = step + 1 if optical > 0.85 else step
    return {"ok": True, "step": step, "next": next_step, "optical": optical, "reason": "ok"}
