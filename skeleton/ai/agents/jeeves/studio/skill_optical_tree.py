"""Unlock skills by optical."""
from __future__ import annotations
from typing import Dict, Any, List

def unlock_skills(optical: float) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "floors", "skills": []}
    skills = ["base_move"]
    if optical > 0.9:
        skills.append("optical_dash")
    return {"ok": True, "skills": skills, "optical": optical, "reason": "ok"}
