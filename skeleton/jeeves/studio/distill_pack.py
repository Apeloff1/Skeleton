"""Distill pack.
Fidelity and optical pack for Jeeves ingest.
"""
from typing import Any, Dict

class DistillPack:
    def emit(self, fidelity: float, optical: float, lenses: list) -> Dict[str, Any]:
        if not isinstance(fidelity, (int, float)) or not isinstance(optical, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.distill.pack.v1"}
        ok = fidelity >= 0.92 and optical >= 0.9
        return {"ok": ok, "fidelity": fidelity, "optical": optical, "lenses": lenses, "ingest_ready": ok, "reason": "ok" if ok else "gates_failed", "schema": "skeleton.distill.pack.v1"}
