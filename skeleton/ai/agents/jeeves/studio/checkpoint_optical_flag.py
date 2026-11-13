"""Flag checkpoint by optical."""
from __future__ import annotations
from typing import Dict, Any

def flag_checkpoint(id: str, optical: float) -> Dict[str, Any]:
    if not id or optical < 0.8:
        return {"ok": False, "reason": "floors", "flagged": False}
    return {"ok": True, "id": id, "optical": optical, "flagged": True, "reason": "ok"}
