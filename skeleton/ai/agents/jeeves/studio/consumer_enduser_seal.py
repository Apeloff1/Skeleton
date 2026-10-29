"""End-user readiness seal for first install."""
from __future__ import annotations
from typing import Dict, Any

def seal_enduser(ai_ok: bool, peak_ok: bool, fidelity: float, optical: float) -> Dict[str, Any]:
    if not ai_ok or not peak_ok or fidelity < 0.92 or optical < 0.9:
        return {"ok": False, "ready": False, "reason": "gates_failed"}
    return {"ok": True, "ready": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
