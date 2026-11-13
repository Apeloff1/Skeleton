"""Optical gate for skills."""
from __future__ import annotations
from typing import Dict, Any, List

def gate_skill(optical: float) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "floors", "skills": []}
    skills = ["base"]
    if optical > 0.9:
        skills.append("optical")
    return {"ok": True, "skills": skills, "optical": optical, "reason": "ok"}
