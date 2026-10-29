"""Apply optical-biased impulse."""
from __future__ import annotations
from typing import Dict, Any

def apply_impulse(force: float, optical: float) -> Dict[str, Any]:
    if force < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "applied": 0.0}
    applied = force * optical
    return {"ok": True, "force": force, "applied": applied, "optical": optical, "reason": "ok"}
