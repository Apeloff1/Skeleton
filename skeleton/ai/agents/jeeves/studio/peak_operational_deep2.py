"""Deep peak operational."""
from __future__ import annotations
from typing import Dict, Any

def peak_deep(fidelity: float, optical: float) -> Dict[str, Any]:
    if fidelity < 0.94 or optical < 0.95:
        return {"ok": False, "reason": "floors", "peak": False}
    return {"ok": True, "fidelity": fidelity, "optical": optical, "peak": True, "reason": "ok"}
