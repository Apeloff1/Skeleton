"""All-in local AI final tier seal."""
from __future__ import annotations
from typing import Dict, Any

def ai_final_allin(tier: str, fidelity: float, optical: float) -> Dict[str, Any]:
    if tier != "final" or fidelity < 0.94 or optical < 0.95:
        return {"ok": False, "reason": "not_sealed", "sealed": False}
    return {"ok": True, "tier": tier, "fidelity": fidelity, "optical": optical, "sealed": True, "reason": "ok"}
