"""Completionist self-test. Verifies sealed pack with full Godot and seals.
"""
from __future__ import annotations
from typing import Dict, Any
from .pipeline_runner import run_end_to_end
from .completionist_packager import package_sealed

def run_completionist_test() -> Dict[str, Any]:
    brief = "ash vault optical boss salvage cutscene finale"
    result = run_end_to_end(brief, "nes_rom_completionist")
    if not result.get("sealed"):
        return {"ok": False, "reason": result.get("reason", "failed"), "sealed": False}
    packed = package_sealed(result)
    ok = (
        result.get("sealed") is True
        and result.get("reason") == "ok"
        and packed.get("ok") is True
        and len(result.get("godot_files", [])) >= 5
        and result.get("optical", 0) >= 0.9
        and result.get("fidelity", 0) >= 0.92
    )
    return {
        "ok": ok,
        "sealed": result.get("sealed"),
        "reason": result.get("reason"),
        "era": result.get("era"),
        "mode": result.get("mode"),
        "godot_count": len(result.get("godot_files", [])),
        "fidelity": result.get("fidelity"),
        "optical": result.get("optical"),
        "phases": result.get("phases"),
        "narrative": result.get("narrative"),
        "pack_ok": packed.get("ok"),
        "status": result.get("status"),
    }
