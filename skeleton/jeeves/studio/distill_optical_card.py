"""Emit distill card with optical."""
from __future__ import annotations
from typing import Dict, Any

def emit_card(fidelity: float, optical: float) -> Dict[str, Any]:
    if fidelity < 0.92 or optical < 0.9:
        return {"ok": False, "reason": "floors", "emitted": False}
    return {"ok": True, "fidelity": fidelity, "optical": optical, "emitted": True, "reason": "ok"}
