"""End-to-end pipeline runner. Brief -> decomp/distill -> IntegratedStudio -> sealed Godot pack.
"""
from __future__ import annotations
from typing import Dict, Any
from .integrated_studio import IntegratedStudio
from .decomp_distill_pipeline import extract_and_distill

def run_end_to_end(brief: str, source: str = "rom_extract") -> Dict[str, Any]:
    if not brief:
        return {"ok": False, "reason": "empty_brief", "sealed": False}
    studio = IntegratedStudio()
    distill = extract_and_distill(source, studio.optical)
    if not distill["ok"]:
        return {"ok": False, "reason": distill["reason"], "sealed": False, "distill": distill}
    result = studio.run_pipeline(brief)
    result["distill"] = distill
    result["sealed"] = result.get("sealed", False) and distill["ok"]
    if result["sealed"]:
        result["reason"] = "ok"
        result["pack"] = {
            "brief": brief,
            "era": result["era"],
            "mode": result["mode"],
            "godot_files": result.get("godot_files", []),
            "fidelity": result["fidelity"],
            "optical": result["optical"],
        }
    return result
