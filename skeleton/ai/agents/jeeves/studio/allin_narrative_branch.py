"""All-in narrative branch selector."""
from __future__ import annotations
from typing import Dict, Any

def narrative_allin(optical: float, salvage: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "branch": "failure"}
    branch = "rich_extract" if optical > 0.92 and salvage > 0.85 else "high_optical" if optical > 0.88 else "standard"
    return {"ok": True, "branch": branch, "optical": optical, "salvage": salvage, "reason": "ok"}
