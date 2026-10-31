"""Deep local AI operational."""
from __future__ import annotations
from typing import Dict, Any

def operational_deep(tier: str, optical: float) -> Dict[str, Any]:
    if tier not in ("draft", "refine", "final") or optical < 0.85:
        return {"ok": False, "reason": "floors", "ready": False}
    return {"ok": True, "tier": tier, "optical": optical, "ready": True, "reason": "ok"}
