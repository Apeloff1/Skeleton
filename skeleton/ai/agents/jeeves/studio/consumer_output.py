"""Consumer output.
Sealed pack output for end users.
"""
from typing import Any, Dict

class ConsumerOutput:
    def pack(self, brief: str, sealed: bool, fidelity: float) -> Dict[str, Any]:
        if not isinstance(brief, str) or not brief.strip():
            return {"ok": False, "reason": "empty_brief", "schema": "skeleton.output.v1"}
        ok = sealed and fidelity >= 0.92
        return {"ok": ok, "brief": brief, "sealed": sealed, "fidelity": fidelity, "reason": "ok" if ok else "gates_failed", "schema": "skeleton.output.v1"}
