"""Final pipeline gate for main readiness."""
from __future__ import annotations
from typing import Dict, Any

def gate_final(ai_ok: bool, peak_ok: bool, export_ok: bool, godot_ok: bool, fidelity: float, optical: float) -> Dict[str, Any]:
    if not (ai_ok and peak_ok and export_ok and godot_ok) or fidelity < 0.92 or optical < 0.9:
        return {"ok": False, "pass": False, "reason": "gates_failed"}
    return {"ok": True, "pass": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
