"""Completionist seal across all layers."""
from __future__ import annotations
from typing import Dict, Any

def seal_completionist(fidelity: float, optical: float, all_ok: bool) -> Dict[str, Any]:
    if fidelity < 0.94 or optical < 0.95 or not all_ok:
        return {"ok": False, "sealed": False, "reason": "incomplete"}
    return {"ok": True, "sealed": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
