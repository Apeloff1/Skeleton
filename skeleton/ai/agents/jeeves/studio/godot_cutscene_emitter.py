"""Emit Godot cutscene script."""
from __future__ import annotations
from typing import Dict, Any

def emit_cutscene(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "script": ""}
    script = "extends Node2D\nfunc _ready():\n    # cutscene sequence for " + era + "\n    pass\n"
    return {"ok": True, "era": era, "script": script, "reason": "ok"}
