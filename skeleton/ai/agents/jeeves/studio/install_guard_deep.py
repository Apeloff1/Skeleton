"""Deep install guard."""
from __future__ import annotations
from typing import Dict, Any

def guard_deep(ai_ok: bool, peak_ok: bool, godot_ok: bool, optical: float, fidelity: float) -> Dict[str, Any]:
    if not (ai_ok and peak_ok and godot_ok) or optical < 0.9 or fidelity < 0.92:
        return {"ok": False, "ready": False, "reason": "gates_failed"}
    return {"ok": True, "ready": True, "optical": optical, "fidelity": fidelity, "reason": "ok"}
