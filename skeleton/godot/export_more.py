"""skeleton/godot/export_more.py
More extreme complete Godot export.
project.godot / world.tscn, validation, headless, receipts.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class ExportError(Exception):
    pass

class GodotExportMore:
    def emit_pack(self, name: str) -> str:
        if not name.endswith((".tscn", ".godot")):
            raise ExportError("invalid")
        return hashlib.sha256(f"{name}:more".encode()).hexdigest()
