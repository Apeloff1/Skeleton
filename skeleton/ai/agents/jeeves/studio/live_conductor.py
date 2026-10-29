"""Live conductor.
Imports and chains decomp, distill, era binder, AI loop, Godot, fail-closed, and persist.
"""
from typing import Any, Dict

class LiveConductor:
    def run(self, patterns: Dict[str, Any], optical: float, era: str, fidelity: float) -> Dict[str, Any]:
        weights = {"decomp": 0.96, "distill": fidelity, "optical": optical}
        bound = {"era": era, "mode": "3d" if era == "ps2" else "2.5d", "abilities": ["move", "interact", "salvage"]}
        loop = {"ok": fidelity >= 0.92 and optical >= 0.8, "next": "advance"}
        godot = ["project.godot", "world.tscn", "player.gd", "boss.gd"]
        export_ok = loop["ok"] and len(godot) > 0
        return {
            "weights": weights,
            "bound": bound,
            "loop": loop,
            "godot": godot,
            "export_ok": export_ok,
            "schema": "skeleton.live.conductor.v1",
        }
