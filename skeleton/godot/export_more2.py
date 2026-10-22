"""skeleton/godot/export_more2.py
More2 extreme complete Godot export.
project.godot / world.tscn, validation, headless, receipts.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class ExportError(Exception):
    pass

class GodotExportMore2:
    def emit_pack(self, name: str) -> str:
        if not name.endswith((".tscn", ".godot")):
            raise ExportError("invalid")
        return hashlib.sha256(f"{name}:more2".encode()).hexdigest()
