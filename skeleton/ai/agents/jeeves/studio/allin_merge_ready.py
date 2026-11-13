"""All-in merge-ready flag."""
from __future__ import annotations
from typing import Dict, Any

def merge_ready_allin(complete: bool, fidelity: float, optical: float) -> Dict[str, Any]:
    if not complete or fidelity < 0.92 or optical < 0.9:
        return {"ok": False, "ready": False, "reason": "not_ready"}
    return {"ok": True, "ready": True, "fidelity": fidelity, "optical": optical, "reason": "ok"}
