"""Fail-closed export gate with all seals."""
from __future__ import annotations
from typing import Dict, Any

def gate_export(fidelity: float, optical: float, godot_ok: bool, ai_ok: bool) -> Dict[str, Any]:
    if fidelity < 0.92 or optical < 0.9 or not godot_ok or not ai_ok:
        return {"ok": False, "exported": False, "reason": "gates_failed"}
    return {"ok": True, "exported": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
