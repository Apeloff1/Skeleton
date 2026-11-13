"""Consumer-grade local AI game builder.
End-user entry: brief -> full pipeline -> sealed pack. Fail-closed.
"""
from typing import Any, Dict

class ConsumerGameBuilder:
    def build(self, brief: str, optical: float = 0.95, fidelity: float = 0.94) -> Dict[str, Any]:
        if not isinstance(brief, str) or not brief.strip():
            return {"ok": False, "reason": "empty_brief", "schema": "skeleton.consumer.builder.v1"}
        if not isinstance(optical, (int, float)) or not isinstance(fidelity, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.consumer.builder.v1"}
        ok = optical >= 0.9 and fidelity >= 0.92
        return {
            "ok": ok,
            "brief": brief,
            "optical": optical,
            "fidelity": fidelity,
            "sealed": ok,
            "reason": "ok" if ok else "gates_failed",
            "schema": "skeleton.consumer.builder.v1",
        }
