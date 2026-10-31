"""Consumer peak seal with all floors."""
from __future__ import annotations
from typing import Dict, Any

def seal_consumer(fidelity: float, optical: float, ai_ok: bool, godot_ok: bool) -> Dict[str, Any]:
    if fidelity < 0.92 or optical < 0.9 or not ai_ok or not godot_ok:
        return {"ok": False, "sealed": False, "reason": "floors_failed"}
    return {"ok": True, "sealed": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
