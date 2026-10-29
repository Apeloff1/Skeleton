"""Emit Godot physics_process with real movement."""
from __future__ import annotations
from typing import Dict, Any

def emit_physics_script(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "script": ""}
    script = "extends Node2D\nfunc _physics_process(delta):\n    position.x += 120 * delta  # era-consistent move\n    if optical > 0.9:\n        position.y += 40 * delta\n"
    return {"ok": True, "era": era, "script": script, "reason": "ok"}
