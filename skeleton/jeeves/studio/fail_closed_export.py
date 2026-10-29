"""Fail-closed export.
Refuses to bundle unless fidelity, validator, and asset floors are met.
"""
from typing import Any, Dict, List

class FailClosedExport:
    def bundle(self, fidelity: float, validator_ok: bool, assets_exported: int, godot: List[str], distill: Dict[str, Any]) -> Dict[str, Any]:
        ok = fidelity >= 0.92 and validator_ok and assets_exported > 0
        return {
            "ok": ok,
            "fidelity": fidelity,
            "validator_ok": validator_ok,
            "assets_exported": assets_exported,
            "godot": godot if ok else [],
            "distill": distill if ok else {},
            "schema": "skeleton.export.failclosed.v1",
        }
