"""All-in boss phase expander."""
from __future__ import annotations
from typing import Dict, Any, List

def boss_allin(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "phases": []}
    phases = ["intro", "mid", "weak_point", "finale"]
    if optical > 0.92:
        phases.append("enrage")
    return {"ok": True, "phases": phases, "optical": optical, "reason": "ok"}
