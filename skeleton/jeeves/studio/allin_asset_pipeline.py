"""All-in asset pipeline gate."""
from __future__ import annotations
from typing import Dict, Any

def asset_allin(fidelity: float, optical: float) -> Dict[str, Any]:
    if fidelity < 0.9 or optical < 0.85:
        return {"ok": False, "reason": "floors", "valid": False}
    return {"ok": True, "fidelity": fidelity, "optical": optical, "valid": True, "reason": "ok"}
