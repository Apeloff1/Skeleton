"""CLI surface for the studio. build / status / seal.
"""
from __future__ import annotations
from typing import Dict, Any
from .pipeline_runner import run_end_to_end
from .integrated_studio import IntegratedStudio

def cli(cmd: str, brief: str = "") -> Dict[str, Any]:
    if not cmd:
        return {"ok": False, "reason": "empty_command"}
    if cmd == "status":
        s = IntegratedStudio()
        return {"ok": True, "status": s.status(), "reason": "ok"}
    if cmd == "build":
        if not brief:
            return {"ok": False, "reason": "empty_brief", "sealed": False}
        return run_end_to_end(brief)
    if cmd == "seal":
        r = run_end_to_end(brief or "default ash vault")
        return {"ok": r.get("sealed", False), "sealed": r.get("sealed", False), "reason": r.get("reason", "unknown")}
    return {"ok": False, "reason": "unknown_command"}
