"""Self-test for the end-to-end pipeline. Call run_selftest() to verify seal.
"""
from __future__ import annotations
from typing import Dict, Any
from .pipeline_runner import run_end_to_end
from .studio_cli import cli

def run_selftest() -> Dict[str, Any]:
    brief = "ash vault with optical boss and salvage"
    result = run_end_to_end(brief, "nes_rom_sim")
    status = cli("status")
    ok = result.get("sealed") is True and result.get("reason") == "ok"
    return {
        "ok": ok,
        "sealed": result.get("sealed", False),
        "reason": result.get("reason", "unknown"),
        "era": result.get("era"),
        "mode": result.get("mode"),
        "godot_count": len(result.get("godot_files", [])),
        "fidelity": result.get("fidelity"),
        "optical": result.get("optical"),
        "status_ready": status.get("status", {}).get("ready", False),
    }
