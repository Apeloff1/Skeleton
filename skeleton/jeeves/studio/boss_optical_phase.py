"""Generate boss phases by optical."""
from __future__ import annotations
from typing import Dict, Any, List

def generate_phases(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "phases": []}
    phases = ["intro", "mid", "finale"]
    if optical > 0.9:
        phases.insert(2, "weak_point")
    return {"ok": True, "phases": phases, "optical": optical, "reason": "ok"}
