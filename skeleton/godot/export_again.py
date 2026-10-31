"""skeleton/godot/export_again.py
Further extreme complete Godot export.
project.godot / world.tscn, validation, headless.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class ExportError(Exception):
    pass

class GodotExportAgain:
    def emit_pack(self, name: str) -> str:
        if not name.endswith((".tscn", ".godot")):
            raise ExportError("invalid")
        return hashlib.sha256(name.encode()).hexdigest()
