"""Seal local AI at final tier."""
from __future__ import annotations
from typing import Dict, Any

def seal_final(tier: str, fidelity: float, optical: float) -> Dict[str, Any]:
    if tier != "final" or fidelity < 0.94 or optical < 0.95:
        return {"ok": False, "reason": "not_final", "sealed": False}
    return {"ok": True, "tier": tier, "fidelity": fidelity, "optical": optical, "sealed": True, "reason": "ok"}
