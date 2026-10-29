"""Expand AI behaviors by optical."""
from __future__ import annotations
from typing import Dict, Any, List

def expand_behaviors(optical: float) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "floors", "behaviors": []}
    behaviors = ["patrol", "chase", "attack"]
    if optical > 0.9:
        behaviors.append("optical_flank")
    return {"ok": True, "behaviors": behaviors, "optical": optical, "reason": "ok"}
