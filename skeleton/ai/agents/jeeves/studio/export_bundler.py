"""Export bundler.
Bundles Godot, distill, and summary with fidelity gate.
"""
from typing import Any, Dict, List

class ExportBundler:
    def bundle(self, fidelity: float, optical: float, godot: List[str], distill: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(fidelity, (int, float)) or not isinstance(optical, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.export.bundle.v1"}
        ok = fidelity >= 0.92 and optical >= 0.9
        return {"ok": ok, "fidelity": fidelity, "optical": optical, "godot": godot if ok else [], "distill": distill if ok else {}, "reason": "ok" if ok else "gates_failed", "schema": "skeleton.export.bundle.v1"}
