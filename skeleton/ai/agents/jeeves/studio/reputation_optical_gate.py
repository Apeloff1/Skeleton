"""Optical gate for reputation."""
from __future__ import annotations
from typing import Dict, Any

def gate_rep(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "rep": 0.0}
    rep = optical * 100
    return {"ok": True, "rep": rep, "optical": optical, "reason": "ok"}
