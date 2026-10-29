"""Select narrative branch from optical and salvage."""
from __future__ import annotations
from typing import Dict, Any

def select_branch(optical: float, salvage: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "branch": "failure"}
    branch = "rich_extract" if optical > 0.92 and salvage > 0.8 else "high_optical" if optical > 0.85 else "standard"
    return {"ok": True, "branch": branch, "optical": optical, "salvage": salvage, "reason": "ok"}
