"""Operational entry point for the studio.
"""
from __future__ import annotations
from typing import Dict, Any
from .integrated_studio import IntegratedStudio
from .local_ai_large_cycle import large_cycle

def run_operational(brief: str) -> Dict[str, Any]:
    if not brief:
        return {"ok": False, "reason": "empty_brief"}
    studio = IntegratedStudio()
    result = studio.run_pipeline(brief)
    ai = large_cycle(brief, studio.optical, studio.fidelity)
    result["entry"] = "operational"
    result["ai_direct"] = ai
    return result
