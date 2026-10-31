"""All-in first-install readiness."""
from __future__ import annotations
from typing import Dict, Any

def install_allin(ai_ok: bool, peak_ok: bool, godot_ok: bool, fidelity: float, optical: float) -> Dict[str, Any]:
    if not (ai_ok and peak_ok and godot_ok) or fidelity < 0.92 or optical < 0.9:
        return {"ok": False, "ready": False, "reason": "gates_failed"}
    return {"ok": True, "ready": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
