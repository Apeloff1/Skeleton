"""End-user peak seal."""
from __future__ import annotations
from typing import Dict, Any

def seal_enduser_peak(ai_ok: bool, peak_ok: bool, export_ok: bool, godot_ok: bool, fidelity: float, optical: float) -> Dict[str, Any]:
    if not (ai_ok and peak_ok and export_ok and godot_ok) or fidelity < 0.94 or optical < 0.95:
        return {"ok": False, "peak": False, "reason": "gates_failed"}
    return {"ok": True, "peak": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
