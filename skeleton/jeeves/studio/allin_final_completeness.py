"""All-in final completeness seal."""
from __future__ import annotations
from typing import Dict, Any

def completeness_allin(fidelity: float, optical: float, ai_ok: bool, peak_ok: bool, export_ok: bool, godot_ok: bool) -> Dict[str, Any]:
    if fidelity < 0.94 or optical < 0.95 or not (ai_ok and peak_ok and export_ok and godot_ok):
        return {"ok": False, "complete": False, "reason": "gates_failed"}
    return {"ok": True, "complete": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
