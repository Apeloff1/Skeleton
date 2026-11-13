"""All-in Godot scene and script emitter."""
from __future__ import annotations
from typing import Dict, Any

def emit_allin(era: str, rooms: int) -> Dict[str, Any]:
    if not era or rooms < 1:
        return {"ok": False, "reason": "floors", "script": ""}
    script = "extends Node2D\nfunc _physics_process(delta):\n    position.x += 100 * delta\n"
    return {"ok": True, "era": era, "rooms": rooms, "script": script, "reason": "ok"}
