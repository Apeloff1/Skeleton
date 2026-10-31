"""Scale conductor — wires agents, seeds, runtimes, and services.
"""
from __future__ import annotations
from typing import Any

from skeleton.jeeves.ecosystem.agents.code_writer import run as code_run
from skeleton.jeeves.ecosystem.agents.level_designer import LeveldesignerAgent
from skeleton.jeeves.ecosystem.procedural.seed_000 import rooms
from skeleton.jeeves.ecosystem.runtime.godot4 import boot, export_manifest
from skeleton.jeeves.ecosystem.microservices.session_service import health as session_health

def run_scale(brief: str, era: str = "ash", optical: float = 0.95) -> dict[str, Any]:
    if not brief or len(brief) < 4:
        return {"ok": False, "reason": "empty_brief", "sealed": False}
    code = code_run(brief, era=era)
    level = LeveldesignerAgent(era=era, optical=optical).build_graph(brief)
    layout = rooms(6, optical)
    runtime = boot({"era": era})
    export = export_manifest([{"path": "project.godot", "content": ""}, {"path": "world.tscn", "content": ""}])
    sealed = all([code.get("ok"), level.get("ok"), runtime.get("ok"), export.get("ok"), session_health().get("ok")])
    return {
        "ok": sealed,
        "sealed": sealed,
        "era": era,
        "rooms": len(layout),
        "code": code,
        "level": level,
        "runtime": runtime,
        "export": export,
        "status": "scale_ready" if sealed else "incomplete",
    }
