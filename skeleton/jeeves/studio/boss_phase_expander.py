"""Expand boss phases from optical and era."""
from __future__ import annotations
from typing import Dict, Any, List

def expand_phases(era: str, optical: float) -> Dict[str, Any]:
    if optical < 0.75 or not era:
        return {"ok": False, "reason": "floors", "phases": []}
    phases = ["intro", "mid", "weak_point", "finale"]
    if optical > 0.9:
        phases.append("enrage")
    return {"ok": True, "era": era, "phases": phases, "optical": optical, "reason": "ok"}
