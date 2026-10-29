"""Export orchestrator.
Bundles Godot files, distill card, summary, and asset pipeline outputs into a single export.
"""
from typing import Any, Dict, List

class ExportOrchestrator:
    def bundle(self, godot_files: List[str], distill: Dict[str, Any], summary: Dict[str, Any], assets: int) -> Dict[str, Any]:
        return {
            "godot": godot_files,
            "distill_ready": distill.get("ingest_ready", False),
            "fidelity": distill.get("fidelity", 0.0),
            "summary_grade": summary.get("grade", "B"),
            "assets_exported": assets,
            "complete": distill.get("ingest_ready", False) and assets > 0,
            "schema": "skeleton.export.v1",
        }
