"""Consumer export.
Fail-closed export for end-user packs.
"""
from typing import Any, Dict

class ConsumerExport:
    def export(self, sealed: bool, fidelity: float, optical: float) -> Dict[str, Any]:
        if not isinstance(fidelity, (int, float)) or not isinstance(optical, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.export.v1"}
        ok = sealed and fidelity >= 0.92 and optical >= 0.9
        return {"ok": ok, "sealed": sealed, "fidelity": fidelity, "optical": optical, "reason": "ok" if ok else "gates_failed", "schema": "skeleton.export.v1"}
