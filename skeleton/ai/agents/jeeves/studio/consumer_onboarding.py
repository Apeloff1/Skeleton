"""Consumer onboarding.
First-run flow: brief, optical, fidelity, seal.
"""
from typing import Any, Dict

class ConsumerOnboarding:
    def start(self, brief: str, optical: float = 0.95, fidelity: float = 0.94) -> Dict[str, Any]:
        if not isinstance(brief, str) or not brief.strip():
            return {"ok": False, "reason": "empty_brief", "schema": "skeleton.onboarding.v1"}
        ok = optical >= 0.9 and fidelity >= 0.92
        return {"ok": ok, "brief": brief, "optical": optical, "fidelity": fidelity, "step": "brief", "sealed": ok, "reason": "ok" if ok else "gates_failed", "schema": "skeleton.onboarding.v1"}
