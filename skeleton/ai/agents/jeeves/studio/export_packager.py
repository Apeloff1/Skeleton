"""Export packager.
Bundles Godot files, distill card, and summary into a single export dict.
"""
from __future__ import annotations
from typing import Any, Dict

class ExportPackager:
    def package(self, godot_files: list, distill_pack: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "schema": "skeleton.export.v1",
            "godot": godot_files,
            "distill": distill_pack,
            "summary": summary,
            "ready": True,
            "stored_prose": 0,
        }
