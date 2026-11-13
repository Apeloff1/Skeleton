"""Integrate physics with optical mass bias."""
from __future__ import annotations
from typing import Dict, Any

def integrate_optical(bodies: int, optical: float) -> Dict[str, Any]:
    if bodies < 1 or optical < 0.7:
        return {"ok": False, "reason": "floors", "integrated": False}
    return {"ok": True, "bodies": bodies, "optical": optical, "integrated": True, "reason": "ok"}
