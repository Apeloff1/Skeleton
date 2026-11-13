"""Final peak seal: all gates must pass."""
from __future__ import annotations
from typing import Dict, Any

def check_peak_seal(fidelity: float, optical: float, ai_ok: bool, export_ok: bool, godot_ok: bool) -> Dict[str, Any]:
    if fidelity < 0.94 or optical < 0.95 or not ai_ok or not export_ok or not godot_ok:
        return {"ok": False, "peak": False, "reason": "gates_failed"}
    return {"ok": True, "peak": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
