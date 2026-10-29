"""Godot header.
Era and mode headers for project.godot.
"""
from typing import Any, Dict

class GodotHeader:
    def emit(self, era: str, mode: str, optical: float) -> Dict[str, Any]:
        if not isinstance(era, str) or not era.strip():
            return {"ok": False, "reason": "empty_era", "schema": "skeleton.godot.header.v1"}
        text = f"[application]\\nconfig/name=\\\"Ash Tunnels {era}\\\"\\n; mode={mode} optical={optical}"
        return {"ok": True, "era": era, "mode": mode, "optical": optical, "text": text, "reason": "ok", "schema": "skeleton.godot.header.v1"}
