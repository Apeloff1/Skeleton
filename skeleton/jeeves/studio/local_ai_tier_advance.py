"""Advance local AI tier by optical."""
from __future__ import annotations
from typing import Dict, Any

def advance_tier(current: str, optical: float) -> Dict[str, Any]:
    if current not in ("draft", "refine", "final") or optical < 0.85:
        return {"ok": False, "reason": "floors", "next": current}
    next_t = "refine" if current == "draft" else "final"
    return {"ok": True, "current": current, "next": next_t, "optical": optical, "reason": "ok"}
