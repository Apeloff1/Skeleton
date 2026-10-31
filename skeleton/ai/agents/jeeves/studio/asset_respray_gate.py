"""Gate asset respray by fidelity."""
from __future__ import annotations
from typing import Dict, Any

def gate_respray(fidelity: float, optical: float) -> Dict[str, Any]:
    if fidelity < 0.9 or optical < 0.85:
        return {"ok": False, "reason": "floors", "resprayed": False}
    return {"ok": True, "fidelity": fidelity, "optical": optical, "resprayed": True, "reason": "ok"}
