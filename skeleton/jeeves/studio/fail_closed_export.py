"""Advanced fail-closed export.
Multi-gate with type guards: fidelity, validator, assets, optical, and ratchet.
"""
from typing import Any, Dict, List

class FailClosedExport:
    def bundle(self, fidelity: float, validator_ok: bool, assets_exported: int, optical: float, ratchet: float, godot: List[str], distill: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(fidelity, (int, float)) or not isinstance(optical, (int, float)) or not isinstance(ratchet, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.export.failclosed.v3"}
        if not isinstance(assets_exported, int) or assets_exported < 0:
            return {"ok": False, "reason": "bad_assets", "schema": "skeleton.export.failclosed.v3"}
        ok = fidelity >= 0.92 and bool(validator_ok) and assets_exported > 0 and optical >= 0.8 and fidelity >= ratchet
        return {
            "ok": ok,
            "fidelity": fidelity,
            "validator_ok": bool(validator_ok),
            "assets_exported": assets_exported,
            "optical": optical,
            "ratchet": ratchet,
            "godot": godot if ok else [],
            "distill": distill if ok else {},
            "reason": "ok" if ok else "gates_failed",
            "schema": "skeleton.export.failclosed.v3",
        }
