"""All-in peak operational seal."""
from __future__ import annotations
from typing import Dict, Any

def peak_allin(fidelity: float, optical: float, export_ok: bool, ai_ok: bool) -> Dict[str, Any]:
    if fidelity < 0.94 or optical < 0.95 or not export_ok or not ai_ok:
        return {"ok": False, "peak": False, "reason": "gates_failed"}
    return {"ok": True, "peak": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
