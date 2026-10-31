"""Asset quality gate.
Fail-closed on fidelity and optical for consumer packs.
"""
from typing import Any, Dict

class AssetQualityGate:
    def check(self, fidelity: float, optical: float, count: int) -> Dict[str, Any]:
        if not isinstance(fidelity, (int, float)) or not isinstance(optical, (int, float)) or not isinstance(count, int):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.asset.quality.v1"}
        ok = fidelity >= 0.92 and optical >= 0.9 and count > 0
        return {
            "ok": ok,
            "fidelity": fidelity,
            "optical": optical,
            "count": count,
            "reason": "ok" if ok else "gates_failed",
            "schema": "skeleton.asset.quality.v1",
        }
